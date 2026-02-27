"""
Cash Risk Service

Builds and persists executive cash-risk snapshots used by CFO dashboards.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.cash_risk_snapshot import CashRiskSnapshot
from app.models.integration_token import IntegrationToken
from app.services.conta_azul_service import (
    ContaAzulAuthError,
    ContaAzulError,
    ContaAzulInvalidGrantError,
    ContaAzulService,
)

logger = logging.getLogger(__name__)

PAID_STATUSES = {"QUITADO", "RECEBIDO", "PAGO", "ACQUITTED", "PAID"}
CANCELED_STATUSES = {"CANCELADO", "CANCELED", "VOID"}


class CashRiskError(Exception):
    """Base exception for cash risk computation errors."""


class CashRiskAuthError(CashRiskError):
    """Raised when Conta Azul authentication is unavailable/invalid."""


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("nome", "descricao", "description", "name", "valor", "status", "id"):
            candidate = value.get(key)
            if candidate:
                return _as_text(candidate)
        parts = [_as_text(v) for v in value.values() if isinstance(v, (str, int, float, bool))]
        return " ".join(p for p in parts if p).strip()
    if isinstance(value, (list, tuple, set)):
        parts = [_as_text(v) for v in value]
        return " ".join(p for p in parts if p).strip()
    return str(value).strip()


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_text(value)
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: Any):
    text = _as_text(value)
    if not text:
        return None
    token = text[:10]
    try:
        return datetime.strptime(token, "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_conta_payload(conta: Dict[str, Any], person_fallback_key: str = "cliente") -> Dict[str, Any]:
    total = _to_float(
        conta.get("valor", 0)
        or conta.get("valor_total", 0)
        or conta.get("amount", 0)
        or conta.get("total", 0)
    )
    nao_pago = _to_float(conta.get("nao_pago"))
    pago = _to_float(conta.get("pago"))
    valor_aberto = nao_pago if nao_pago > 0 else max(total - pago, 0.0)

    status_raw = _as_text(conta.get("status", "")).upper()
    status_traduzido = _as_text(conta.get("status_traduzido", "")).upper()
    status_conta = status_traduzido or status_raw

    vencimento = _as_text(conta.get("data_vencimento", "") or conta.get("due_date", "") or "")
    descricao = _as_text(
        conta.get("descricao", "")
        or conta.get("description", "")
        or conta.get("observacao", "")
        or "Sem descrição"
    )
    pessoa = conta.get("pessoa", {}) or {}
    pessoa_nome = pessoa.get("nome", "") if isinstance(pessoa, dict) else pessoa
    nome_pessoa = (
        _as_text(pessoa_nome)
        or _as_text(conta.get("nome_pessoa", ""))
        or _as_text(conta.get(person_fallback_key, ""))
    )

    return {
        "total": total,
        "nao_pago": nao_pago,
        "pago": pago,
        "valor_aberto": valor_aberto,
        "status": status_conta,
        "vencimento": vencimento,
        "descricao": descricao,
        "nome_pessoa": nome_pessoa,
    }


def _summarize_contas_receber(contas: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    next_7 = today + timedelta(days=7)

    total_atrasado = 0.0
    total_hoje = 0.0
    total_7 = 0.0
    total_pendente = 0.0
    total_quitado = 0.0

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="cliente")
        due_date = _parse_date(payload["vencimento"])

        if payload["status"] in PAID_STATUSES or (payload["valor_aberto"] <= 0 and payload["pago"] > 0):
            total_quitado += max(payload["pago"], payload["total"])
            continue
        if payload["status"] in CANCELED_STATUSES:
            continue

        if due_date and due_date < today:
            total_atrasado += payload["valor_aberto"]
        elif due_date and due_date == today:
            total_hoje += payload["valor_aberto"]
        elif due_date and due_date <= next_7:
            total_7 += payload["valor_aberto"]
        else:
            total_pendente += payload["valor_aberto"]

    total_aberto = total_atrasado + total_hoje + total_7 + total_pendente
    return {
        "total_atrasado": total_atrasado,
        "total_hoje": total_hoje,
        "total_7": total_7,
        "total_pendente": total_pendente,
        "total_quitado": total_quitado,
        "total_aberto": total_aberto,
    }


def _summarize_contas_pagar(contas: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.now(timezone.utc).date()

    total_atrasado = 0.0
    total_pendente = 0.0
    total_quitado = 0.0

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="fornecedor")
        due_date = _parse_date(payload["vencimento"])

        if payload["status"] in PAID_STATUSES or (payload["valor_aberto"] <= 0 and payload["pago"] > 0):
            total_quitado += max(payload["pago"], payload["total"])
            continue
        if payload["status"] in CANCELED_STATUSES:
            continue

        if due_date and due_date < today:
            total_atrasado += payload["valor_aberto"]
        else:
            total_pendente += payload["valor_aberto"]

    return {
        "total_atrasado": total_atrasado,
        "total_pendente": total_pendente,
        "total_quitado": total_quitado,
        "total_aberto": total_atrasado + total_pendente,
    }


def _compute_top_receber_concentration(contas: List[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    total_open = 0.0
    by_client: Dict[str, float] = {}

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="cliente")
        if payload["status"] in PAID_STATUSES or payload["status"] in CANCELED_STATUSES:
            continue
        value_open = float(payload["valor_aberto"] or 0)
        if value_open <= 0:
            continue

        client_name = _as_text(payload["nome_pessoa"]) or _as_text(payload["descricao"]) or "N/A"
        by_client[client_name] = by_client.get(client_name, 0.0) + value_open
        total_open += value_open

    ranked = sorted(by_client.items(), key=lambda item: item[1], reverse=True)
    top_clients = ranked[:top_n]
    top_sum = sum(value for _, value in top_clients)
    top_pct = (top_sum / total_open * 100.0) if total_open > 0 else 0.0

    return {
        "total_open": total_open,
        "top_clients": [{"name": name, "value": value} for name, value in top_clients],
        "top_sum": top_sum,
        "top_pct": top_pct,
    }


async def _fetch_financial_items_paginated(
    service: ContaAzulService,
    access_token: str,
    endpoint: str,
    data_vencimento_de: Optional[str] = None,
    data_vencimento_ate: Optional[str] = None,
    status_filter: Optional[str] = None,
    max_records: int = 500,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    page = 1
    page_size = max(1, min(page_size, 100))
    max_records = max(1, max_records)

    while len(all_items) < max_records:
        request_size = min(page_size, max_records - len(all_items))
        params: Dict[str, Any] = {"pagina": page, "tamanho_pagina": request_size}
        if status_filter:
            params["status"] = status_filter
        if data_vencimento_de:
            params["data_vencimento_de"] = data_vencimento_de
        if data_vencimento_ate:
            params["data_vencimento_ate"] = data_vencimento_ate

        response = await service.make_api_request(
            endpoint=endpoint,
            access_token=access_token,
            method="GET",
            params=params,
        )
        items = service._extract_items(response)
        if not items:
            break

        all_items.extend(items)
        if len(items) < request_size:
            break
        page += 1

    return all_items[:max_records]


_BALANCE_KEYS = (
    "saldo_atual",
    "saldo",
    "valor",
    "balance",
    "saldoAtual",
    "saldo_disponivel",
    "saldoDisponivel",
)


def _extract_balance_value(payload: Any) -> float:
    if isinstance(payload, dict):
        for key in _BALANCE_KEYS:
            if key in payload and payload.get(key) is not None:
                return _to_float(payload.get(key))
        nested = payload.get("saldo")
        if isinstance(nested, dict):
            for key in _BALANCE_KEYS:
                if key in nested and nested.get(key) is not None:
                    return _to_float(nested.get(key))
        return 0.0
    return _to_float(payload)


async def _resolve_conta_saldo(service: ContaAzulService, access_token: str, conta: Dict[str, Any]) -> float:
    conta_id = conta.get("id")
    if conta_id:
        for attempt in range(3):
            try:
                saldo_data = await service.get_saldo_conta(access_token, str(conta_id))
                value = _extract_balance_value(saldo_data)
                return value
            except Exception as exc:
                msg = _as_text(exc).lower()
                if ("429" in msg or "spike" in msg) and attempt < 2:
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue
                break
    return _extract_balance_value(conta)


def _classify_cash_risk(
    saldo_total: float,
    projected_15d: float,
    payable_15d: float,
    concentration_top_pct: float,
    overdue_ratio_pct: float,
) -> Dict[str, Any]:
    coverage = projected_15d / payable_15d if payable_15d > 0 else 1.0

    # Score components (0-100)
    if projected_15d < 0 or saldo_total < 0:
        risk_saldo = 100.0
    else:
        risk_saldo = 0.0 if coverage >= 1 else min(100.0, max(0.0, (1 - coverage) * 100))
    risk_atraso = min(100.0, max(0.0, overdue_ratio_pct))
    risk_concentracao = min(100.0, max(0.0, concentration_top_pct))

    score = (0.40 * risk_saldo) + (0.35 * risk_atraso) + (0.25 * risk_concentracao)

    if score >= 65 or projected_15d < 0 or saldo_total < 0:
        level = "alto"
    elif score >= 35:
        level = "medio"
    else:
        level = "baixo"

    # Guardrail executivo: concentração > 60% nunca pode ser "baixo"
    if concentration_top_pct > 60 and level == "baixo":
        level = "medio"
    if concentration_top_pct >= 75 and level != "alto":
        level = "alto"

    if level == "alto":
        emoji = "🔴"
        recommendation = "Priorize cobrança imediata, reduza concentração e postergue saídas não críticas."
    elif level == "medio":
        emoji = "🟡"
        recommendation = "Acelere recebimentos e execute plano de redução de concentração da carteira."
    else:
        emoji = "🟢"
        recommendation = "Manter ritmo atual, monitorando concentração e atrasos semanalmente."

    return {
        "level": level,
        "emoji": emoji,
        "score": round(score, 2),
        "recommendation": recommendation,
    }


async def _get_valid_conta_azul_token(db: Session) -> str:
    token_record = db.query(IntegrationToken).filter_by(service="conta_azul").first()
    if not token_record:
        raise CashRiskAuthError(
            "Conta Azul não conectado. Autorize em GET /api/auth/conta-azul/authorize"
        )

    if token_record.is_expired():
        try:
            service = ContaAzulService()
            token_data = await service.refresh_access_token(token_record.refresh_token)
            token_record.access_token = token_data["access_token"]
            token_record.refresh_token = token_data.get("refresh_token", token_record.refresh_token)
            token_record.expires_at = datetime.fromisoformat(token_data["expires_at"])
            db.commit()
        except ContaAzulInvalidGrantError:
            raise CashRiskAuthError(
                "Refresh token inválido (invalid_grant). Reautorize em GET /api/auth/conta-azul/authorize"
            )
        except ContaAzulAuthError as exc:
            raise CashRiskAuthError(f"Falha ao renovar token Conta Azul: {exc}")

    return token_record.access_token


async def _build_live_cash_risk_snapshot(db: Session) -> Dict[str, Any]:
    access_token = await _get_valid_conta_azul_token(db)
    service = ContaAzulService()

    today = datetime.now(timezone.utc).date()
    data_de = today.isoformat()
    data_15 = (today + timedelta(days=15)).isoformat()
    data_30 = (today + timedelta(days=30)).isoformat()

    contas_financeiras = await service.get_contas_financeiras(access_token=access_token)
    saldo_total = 0.0
    for conta in contas_financeiras:
        ativo = conta.get("ativo", True)
        if isinstance(ativo, str):
            ativo = ativo.lower() != "false"
        if not ativo:
            continue
        saldo_total += await _resolve_conta_saldo(service, access_token, conta)

    receber_15 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_15,
        max_records=500,
    )
    pagar_15 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_15,
        max_records=500,
    )
    receber_30 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_30,
        max_records=500,
    )

    receber_summary_15 = _summarize_contas_receber(receber_15)
    pagar_summary_15 = _summarize_contas_pagar(pagar_15)
    receber_summary_30 = _summarize_contas_receber(receber_30)
    concentration = _compute_top_receber_concentration(receber_30, top_n=3)

    total_receber_15 = float(receber_summary_15["total_aberto"])
    total_pagar_15 = float(pagar_summary_15["total_aberto"])
    projected_15d = saldo_total + total_receber_15 - total_pagar_15

    overdue_ratio_pct = (
        (float(receber_summary_30["total_atrasado"]) / float(receber_summary_30["total_aberto"])) * 100
        if float(receber_summary_30["total_aberto"]) > 0
        else 0.0
    )
    risk = _classify_cash_risk(
        saldo_total=saldo_total,
        projected_15d=projected_15d,
        payable_15d=total_pagar_15,
        concentration_top_pct=float(concentration["top_pct"]),
        overdue_ratio_pct=overdue_ratio_pct,
    )

    return {
        "snapshot_date": today.isoformat(),
        "saldo_total": round(saldo_total, 2),
        "receber_15": round(total_receber_15, 2),
        "pagar_15": round(total_pagar_15, 2),
        "projected_15d": round(projected_15d, 2),
        "top3_concentration_pct": round(float(concentration["top_pct"]), 2),
        "top3_clients": concentration["top_clients"],
        "overdue_ratio_pct": round(overdue_ratio_pct, 2),
        "risk_score": risk["score"],
        "risk_level": risk["level"],
        "risk_emoji": risk["emoji"],
        "recommendation": risk["recommendation"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _snapshot_row_to_dict(row: CashRiskSnapshot, source: str = "cached") -> Dict[str, Any]:
    return {
        "snapshot_date": row.snapshot_date.isoformat() if row.snapshot_date else None,
        "saldo_total": float(row.saldo_total or 0),
        "receber_15": float(row.receber_15 or 0),
        "pagar_15": float(row.pagar_15 or 0),
        "projected_15d": float(row.projected_15d or 0),
        "top3_concentration_pct": float(row.top3_concentration_pct or 0),
        "risk_score": float(row.risk_score or 0),
        "risk_level": row.risk_level,
        "risk_emoji": row.risk_emoji,
        "recommendation": row.recommendation,
        "source": source,
        "generated_at": row.updated_at.isoformat() if row.updated_at else row.created_at.isoformat(),
    }


async def get_or_build_cash_risk_snapshot(
    db: Session,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    today = date.today()

    current = db.query(CashRiskSnapshot).filter(CashRiskSnapshot.snapshot_date == today).first()
    if current and not force_refresh:
        return _snapshot_row_to_dict(current, source="cached")

    live = await _build_live_cash_risk_snapshot(db)

    if current:
        current.saldo_total = live["saldo_total"]
        current.receber_15 = live["receber_15"]
        current.pagar_15 = live["pagar_15"]
        current.projected_15d = live["projected_15d"]
        current.top3_concentration_pct = live["top3_concentration_pct"]
        current.risk_score = live["risk_score"]
        current.risk_level = live["risk_level"]
        current.risk_emoji = live["risk_emoji"]
        current.recommendation = live["recommendation"]
        row = current
    else:
        row = CashRiskSnapshot(
            snapshot_date=today,
            saldo_total=live["saldo_total"],
            receber_15=live["receber_15"],
            pagar_15=live["pagar_15"],
            projected_15d=live["projected_15d"],
            top3_concentration_pct=live["top3_concentration_pct"],
            risk_score=live["risk_score"],
            risk_level=live["risk_level"],
            risk_emoji=live["risk_emoji"],
            recommendation=live["recommendation"],
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    payload = _snapshot_row_to_dict(row, source="live")
    payload["top3_clients"] = live.get("top3_clients", [])
    payload["overdue_ratio_pct"] = live.get("overdue_ratio_pct", 0.0)
    payload["generated_at"] = live.get("generated_at", payload.get("generated_at"))
    return payload


def get_cash_risk_history(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    history_days = max(1, days)
    cutoff = date.today() - timedelta(days=history_days - 1)
    rows = (
        db.query(CashRiskSnapshot)
        .filter(CashRiskSnapshot.snapshot_date >= cutoff)
        .order_by(CashRiskSnapshot.snapshot_date.desc())
        .all()
    )
    return [_snapshot_row_to_dict(row, source="historical") for row in rows]


def _compute_cash_risk_trend(
    snapshot: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute trend signals from current snapshot vs previous day.

    Returns deltas and direction:
    - improving: risk score dropped materially
    - worsening: risk score increased materially
    - stable: small variation
    - insufficient_data: no prior snapshot available
    """
    current_date = _as_text(snapshot.get("snapshot_date"))
    previous = next(
        (
            item
            for item in history
            if _as_text(item.get("snapshot_date")) and _as_text(item.get("snapshot_date")) != current_date
        ),
        None,
    )

    recent = history[:7] if history else []
    avg_risk_7d = round(
        sum(_to_float(item.get("risk_score")) for item in recent) / len(recent),
        2,
    ) if recent else None
    avg_projected_7d = round(
        sum(_to_float(item.get("projected_15d")) for item in recent) / len(recent),
        2,
    ) if recent else None

    if not previous:
        return {
            "direction": "insufficient_data",
            "previous_snapshot_date": None,
            "risk_score_delta": None,
            "projected_15d_delta": None,
            "saldo_total_delta": None,
            "top3_concentration_delta_pct": None,
            "risk_level_changed": False,
            "avg_risk_score_7d": avg_risk_7d,
            "avg_projected_15d_7d": avg_projected_7d,
        }

    risk_score_delta = round(
        _to_float(snapshot.get("risk_score")) - _to_float(previous.get("risk_score")),
        2,
    )
    projected_delta = round(
        _to_float(snapshot.get("projected_15d")) - _to_float(previous.get("projected_15d")),
        2,
    )
    saldo_total_delta = round(
        _to_float(snapshot.get("saldo_total")) - _to_float(previous.get("saldo_total")),
        2,
    )
    concentration_delta = round(
        _to_float(snapshot.get("top3_concentration_pct")) - _to_float(previous.get("top3_concentration_pct")),
        2,
    )

    if risk_score_delta <= -2.0:
        direction = "improving"
    elif risk_score_delta >= 2.0:
        direction = "worsening"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "previous_snapshot_date": _as_text(previous.get("snapshot_date")) or None,
        "risk_score_delta": risk_score_delta,
        "projected_15d_delta": projected_delta,
        "saldo_total_delta": saldo_total_delta,
        "top3_concentration_delta_pct": concentration_delta,
        "risk_level_changed": _as_text(snapshot.get("risk_level")) != _as_text(previous.get("risk_level")),
        "avg_risk_score_7d": avg_risk_7d,
        "avg_projected_15d_7d": avg_projected_7d,
    }


async def get_cash_risk_dashboard_data(
    db: Session,
    force_refresh: bool = False,
    history_days: int = 30,
) -> Dict[str, Any]:
    snapshot = await get_or_build_cash_risk_snapshot(db=db, force_refresh=force_refresh)
    history = get_cash_risk_history(db=db, days=history_days)
    trend = _compute_cash_risk_trend(snapshot=snapshot, history=history)
    return {
        "snapshot": snapshot,
        "history": history,
        "trend": trend,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def persist_daily_cash_risk_snapshot() -> Dict[str, Any]:
    """
    Scheduler entrypoint: persists daily cash-risk snapshot in the database.
    """
    db = SessionLocal()
    try:
        result = await get_or_build_cash_risk_snapshot(db=db, force_refresh=True)
        logger.info(
            "Cash risk snapshot persisted for %s (level=%s score=%.2f)",
            result.get("snapshot_date"),
            result.get("risk_level"),
            float(result.get("risk_score", 0)),
        )
        return result
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist daily cash risk snapshot: %s", exc, exc_info=True)
        raise
    finally:
        db.close()
