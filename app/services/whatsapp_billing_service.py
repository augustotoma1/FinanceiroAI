"""
WhatsApp Billing Service

Builds and dispatches receivable reminders via WhatsApp providers.
"""

from __future__ import annotations

import logging
import re
import hashlib
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.client import Client
from app.models.conversation import Conversation
from app.models.financial_record import FinancialRecord

logger = logging.getLogger(__name__)

_PAID_OR_CANCELED = {
    "paid",
    "pago",
    "quitado",
    "recebido",
    "acquitted",
    "cancelled",
    "canceled",
    "cancelado",
    "void",
}

_SUPPORTED_PROVIDERS = {"log", "waha"}
_WA_BLOCK_STATE_PREFIX = "wae-"
_WA_ERROR_NO_LID = "no_lid"
_WA_ERROR_TIMEOUT = "timeout"
_WA_ERROR_AUTH = "auth"
_WA_ERROR_RATE_LIMIT = "rate_limit"
_WA_ERROR_UNKNOWN = "unknown"


class WhatsAppBillingError(Exception):
    """Base exception for WhatsApp billing failures."""


def _conversation_state_id(prefix: str, raw_key: str) -> str:
    """Build deterministic state id under Conversation.id varchar(36) limit."""
    normalized_prefix = _as_text(prefix) or "wa"
    normalized_key = _as_text(raw_key)
    candidate = f"{normalized_prefix}{normalized_key}"
    if len(candidate) <= 36:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:36 - len(normalized_prefix)]
    return f"{normalized_prefix}{digest}"


def _block_state_id(phone: str) -> str:
    return _conversation_state_id(_WA_BLOCK_STATE_PREFIX, phone)


def _parse_dt(value: Any) -> Optional[datetime]:
    text = _as_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _format_dt(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _classify_send_error(exc_text: str) -> str:
    text = _as_text(exc_text).lower()
    if "no lid for user" in text or "no lid" in text:
        return _WA_ERROR_NO_LID
    if "401" in text or "unauthorized" in text:
        return _WA_ERROR_AUTH
    if "429" in text or "rate limit" in text:
        return _WA_ERROR_RATE_LIMIT
    if "timeout" in text or "timed out" in text:
        return _WA_ERROR_TIMEOUT
    return _WA_ERROR_UNKNOWN


def _load_phone_blocks(db: Session, *, now_utc: datetime) -> Dict[str, Dict[str, Any]]:
    """Load active blocked phones caused by previous WAHA hard failures."""
    block_records = (
        db.query(Conversation)
        .filter(Conversation.id.like(f"{_WA_BLOCK_STATE_PREFIX}%"))
        .all()
    )

    blocked: Dict[str, Dict[str, Any]] = {}
    for record in block_records:
        data = record.data or {}
        if not isinstance(data, dict):
            continue
        phone = _normalize_phone_br(data.get("phone"))
        if not phone:
            continue
        blocked_until = _parse_dt(data.get("blocked_until"))
        if blocked_until and blocked_until <= now_utc:
            continue
        blocked[phone] = {
            "reason": _as_text(data.get("reason")) or _WA_ERROR_UNKNOWN,
            "blocked_until": blocked_until,
            "fail_count": int(data.get("fail_count") or 1),
            "last_error": _as_text(data.get("last_error")),
        }
    return blocked


def _upsert_phone_block(
    db: Session,
    *,
    phone: str,
    reason: str,
    error_message: str,
    now_utc: datetime,
) -> None:
    """Persist/update phone block state for noisy hard failures."""
    state_id = _block_state_id(phone)
    record = db.query(Conversation).filter(Conversation.id == state_id).first()
    previous_data = record.data if record and isinstance(record.data, dict) else {}
    previous_fail_count = int(previous_data.get("fail_count") or 0)
    cooldown_days = max(int(getattr(settings, "WHATSAPP_BILLING_NO_LID_COOLDOWN_DAYS", 30)), 1)
    blocked_until = now_utc + timedelta(days=cooldown_days)

    payload = {
        "type": "whatsapp_error_state",
        "phone": phone,
        "reason": reason,
        "fail_count": previous_fail_count + 1,
        "blocked_until": _format_dt(blocked_until),
        "last_error": _as_text(error_message)[:500],
        "updated_at": _format_dt(now_utc),
    }

    if record:
        record.messages = []
        record.complete = False
        record.data = payload
        record.updated_at = now_utc
    else:
        db.add(
            Conversation(
                id=state_id,
                messages=[],
                complete=False,
                data=payload,
            )
        )
    db.commit()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    text = _as_text(value).replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_brl(value: float) -> str:
    number = f"{value:,.2f}"
    return "R$ " + number.replace(",", "_").replace(".", ",").replace("_", ".")


def _normalize_provider(raw_provider: Optional[str]) -> str:
    provider = (raw_provider or "log").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        logger.warning("Unknown WHATSAPP_BILLING_PROVIDER '%s'. Falling back to 'log'.", provider)
        return "log"
    return provider


def _normalize_phone_br(raw_phone: Any) -> str:
    digits = re.sub(r"\D", "", _as_text(raw_phone))
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) in (10, 11):
        return f"55{digits}"
    return digits


def _classify_escalation_level(
    *,
    due_date: date,
    today: date,
    due_soon_days: int,
    overdue_max_days: int,
) -> Optional[int]:
    delta = (due_date - today).days
    if delta >= 0:
        if delta <= due_soon_days:
            return 1
        return None
    overdue_days = abs(delta)
    if overdue_days > overdue_max_days:
        return None
    if overdue_days >= 8:
        return 3
    return 2


def _build_message(reminder: Dict[str, Any]) -> str:
    level = int(reminder["level"])
    if level == 3:
        intro = "Alerta financeiro AISATEC: títulos em atraso crítico."
    elif level == 2:
        intro = "Aviso financeiro AISATEC: títulos em atraso."
    else:
        intro = "Lembrete financeiro AISATEC: vencimentos próximos."

    lines = [intro, ""]
    for idx, item in enumerate(reminder["items"][:8], 1):
        lines.append(
            f"{idx}) {item['transaction_number']} | venc {item['due_date']} | {_format_brl(item['amount'])}"
        )
    if len(reminder["items"]) > 8:
        lines.append(f"... e mais {len(reminder['items']) - 8} título(s).")
    lines.append("")
    lines.append(f"Total em aberto: {_format_brl(reminder['total_amount'])}")
    lines.append("Se o pagamento já foi realizado, desconsidere esta mensagem.")
    lines.append("Dúvidas: responda neste canal.")
    return "\n".join(lines)


def _collect_reminders(
    db: Session,
    *,
    today: date,
    due_soon_days: int,
    overdue_max_days: int,
    max_messages_per_run: int,
) -> Dict[str, Any]:
    records = (
        db.query(FinancialRecord, Client)
        .join(Client, FinancialRecord.client_id == Client.id)
        .filter(
            FinancialRecord.transaction_type == "receivable",
            FinancialRecord.due_date.isnot(None),
        )
        .all()
    )

    evaluated_records = len(records)
    eligible_records = 0
    skipped_missing_phone = 0
    reminders_by_phone: Dict[str, Dict[str, Any]] = {}

    for financial, client in records:
        status = _as_text(financial.status).lower()
        if status in _PAID_OR_CANCELED:
            continue

        if not financial.due_date:
            continue

        level = _classify_escalation_level(
            due_date=financial.due_date,
            today=today,
            due_soon_days=due_soon_days,
            overdue_max_days=overdue_max_days,
        )
        if level is None:
            continue

        normalized_phone = _normalize_phone_br(client.phone)
        if not normalized_phone:
            skipped_missing_phone += 1
            continue

        eligible_records += 1
        bucket = reminders_by_phone.setdefault(
            normalized_phone,
            {
                "client_name": _as_text(client.name) or "Cliente",
                "to_phone": normalized_phone,
                "level": level,
                "items": [],
                "total_amount": 0.0,
            },
        )
        bucket["level"] = max(bucket["level"], level)
        amount = _to_float(financial.amount)
        bucket["total_amount"] += amount
        bucket["items"].append(
            {
                "transaction_number": _as_text(financial.transaction_number) or f"TX-{financial.id}",
                "due_date": financial.due_date.isoformat(),
                "amount": amount,
            }
        )

    reminders = list(reminders_by_phone.values())
    for reminder in reminders:
        reminder["items"] = sorted(reminder["items"], key=lambda item: item["due_date"])

    reminders = sorted(
        reminders,
        key=lambda reminder: (-int(reminder["level"]), -float(reminder["total_amount"])),
    )[: max(1, max_messages_per_run)]

    level_counts = {"1": 0, "2": 0, "3": 0}
    for reminder in reminders:
        level_counts[str(reminder["level"])] += 1

    return {
        "reminders": reminders,
        "evaluated_records": evaluated_records,
        "eligible_records": eligible_records,
        "eligible_clients": len(reminders),
        "skipped_missing_phone": skipped_missing_phone,
        "level_counts": level_counts,
    }


async def _dispatch_waha_text(*, to_phone: str, text: str) -> None:
    base_url = _as_text(settings.WHATSAPP_WAHA_URL).rstrip("/")
    if not base_url:
        raise WhatsAppBillingError("Missing WHATSAPP_WAHA_URL")

    payload: Dict[str, Any] = {
        "chatId": f"{to_phone}@c.us",
        "text": text,
        "session": _as_text(settings.WHATSAPP_WAHA_SESSION) or "default",
    }

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    api_key = _as_text(settings.WHATSAPP_WAHA_API_KEY)
    if api_key:
        headers["X-Api-Key"] = api_key

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/api/sendText",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 300:
        snippet = _as_text(response.text)[:250]
        raise WhatsAppBillingError(
            f"WAHA send failed ({response.status_code}): {snippet}"
        )


async def run_whatsapp_billing_campaign(
    *,
    db: Optional[Session] = None,
    today: Optional[date] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """Execute one WhatsApp billing campaign pass."""
    started_at = datetime.now(timezone.utc)
    own_session = db is None
    session = db or SessionLocal()
    errors: List[str] = []

    provider = _normalize_provider(settings.WHATSAPP_BILLING_PROVIDER)
    effective_dry_run = settings.WHATSAPP_BILLING_DRY_RUN if dry_run is None else bool(dry_run)
    run_date = today or datetime.now(timezone.utc).date()
    due_soon_days = max(int(settings.WHATSAPP_BILLING_DUE_SOON_DAYS), 0)
    overdue_max_days = max(int(settings.WHATSAPP_BILLING_OVERDUE_MAX_DAYS), 1)
    max_messages_per_run = max(int(settings.WHATSAPP_BILLING_MAX_MESSAGES_PER_RUN), 1)
    skip_no_lid = bool(getattr(settings, "WHATSAPP_BILLING_SKIP_NO_LID", True))
    now_utc = datetime.now(timezone.utc)

    messages_sent = 0
    messages_dry_run = 0
    messages_failed = 0
    skipped_blocked_phone = 0
    error_type_counts: Dict[str, int] = {
        _WA_ERROR_NO_LID: 0,
        _WA_ERROR_TIMEOUT: 0,
        _WA_ERROR_AUTH: 0,
        _WA_ERROR_RATE_LIMIT: 0,
        _WA_ERROR_UNKNOWN: 0,
    }

    try:
        summary = _collect_reminders(
            session,
            today=run_date,
            due_soon_days=due_soon_days,
            overdue_max_days=overdue_max_days,
            max_messages_per_run=max_messages_per_run,
        )
        reminders = summary["reminders"]
        blocked_by_phone = _load_phone_blocks(session, now_utc=now_utc)
        blocked_targets_preview: List[Dict[str, Any]] = []
        active_reminders: List[Dict[str, Any]] = []
        for reminder in reminders:
            phone = _as_text(reminder.get("to_phone"))
            block = blocked_by_phone.get(phone)
            if block:
                skipped_blocked_phone += 1
                blocked_targets_preview.append(
                    {
                        "client_name": _as_text(reminder.get("client_name")) or "Cliente",
                        "to_phone": phone,
                        "reason": _as_text(block.get("reason")) or _WA_ERROR_UNKNOWN,
                        "blocked_until": _format_dt(block["blocked_until"])
                        if isinstance(block.get("blocked_until"), datetime)
                        else None,
                        "total_amount": round(float(reminder.get("total_amount") or 0.0), 2),
                    }
                )
                continue
            active_reminders.append(reminder)

        reminders = active_reminders
        targets_preview: List[Dict[str, Any]] = []
        for reminder in reminders:
            items = reminder.get("items") or []
            first_due = items[0]["due_date"] if items else None
            last_due = items[-1]["due_date"] if items else None
            targets_preview.append(
                {
                    "client_name": _as_text(reminder.get("client_name")) or "Cliente",
                    "to_phone": _as_text(reminder.get("to_phone")),
                    "level": int(reminder.get("level") or 1),
                    "items_count": len(items),
                    "total_amount": round(float(reminder.get("total_amount") or 0.0), 2),
                    "oldest_due_date": first_due,
                    "latest_due_date": last_due,
                }
            )

        send_enabled = provider == "waha" and not effective_dry_run
        if provider == "waha" and send_enabled and not _as_text(settings.WHATSAPP_WAHA_URL):
            errors.append("Missing WHATSAPP_WAHA_URL for waha provider.")
            send_enabled = False

        for reminder in reminders:
            text = _build_message(reminder)

            if not send_enabled:
                messages_dry_run += 1
                logger.info(
                    "[whatsapp-billing dry-run] to=%s level=%s total=%s items=%s",
                    reminder["to_phone"],
                    reminder["level"],
                    _format_brl(float(reminder["total_amount"])),
                    len(reminder["items"]),
                )
                continue

            try:
                await _dispatch_waha_text(to_phone=reminder["to_phone"], text=text)
                messages_sent += 1
            except Exception as exc:  # pragma: no cover - defensive guard
                messages_failed += 1
                raw_error = _as_text(exc)
                error_kind = _classify_send_error(raw_error)
                error_type_counts[error_kind] = int(error_type_counts.get(error_kind, 0)) + 1
                if error_kind == _WA_ERROR_NO_LID and skip_no_lid:
                    try:
                        _upsert_phone_block(
                            session,
                            phone=_as_text(reminder.get("to_phone")),
                            reason=_WA_ERROR_NO_LID,
                            error_message=raw_error,
                            now_utc=now_utc,
                        )
                    except Exception:
                        logger.warning("Failed to persist WhatsApp block state", exc_info=True)

                error_message = (
                    f"Failed WhatsApp to {reminder['to_phone']} ({error_kind}): {raw_error}"
                )
                errors.append(error_message)
                logger.error(error_message)

        success = len(errors) == 0
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        return {
            "success": success,
            "provider": provider,
            "dry_run": not send_enabled,
            "evaluated_records": summary["evaluated_records"],
            "eligible_records": summary["eligible_records"],
            "eligible_clients": len(reminders),
            "skipped_missing_phone": summary["skipped_missing_phone"],
            "skipped_blocked_phone": skipped_blocked_phone,
            "level_counts": summary["level_counts"],
            "messages_sent": messages_sent,
            "messages_dry_run": messages_dry_run,
            "messages_failed": messages_failed,
            "error_type_counts": error_type_counts,
            "blocked_phone_count": len(blocked_by_phone),
            "blocked_targets_preview": blocked_targets_preview,
            "targets_preview": targets_preview,
            "errors": errors,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if own_session:
            session.close()


def list_blocked_whatsapp_targets(*, db: Optional[Session] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return active blocked WhatsApp targets stored from previous hard failures."""
    own_session = db is None
    session = db or SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        blocked = _load_phone_blocks(session, now_utc=now_utc)
        items = []
        for phone, state in blocked.items():
            blocked_until = state.get("blocked_until")
            items.append(
                {
                    "phone": phone,
                    "reason": _as_text(state.get("reason")) or _WA_ERROR_UNKNOWN,
                    "blocked_until": _format_dt(blocked_until)
                    if isinstance(blocked_until, datetime)
                    else None,
                    "fail_count": int(state.get("fail_count") or 1),
                    "last_error": _as_text(state.get("last_error"))[:200],
                }
            )
        items.sort(key=lambda item: (item.get("blocked_until") or "", item.get("phone") or ""))
        return items[: max(1, limit)]
    finally:
        if own_session:
            session.close()


def clear_blocked_whatsapp_targets(
    *,
    phones: Optional[List[str]] = None,
    clear_all: bool = False,
    db: Optional[Session] = None,
) -> int:
    """Clear blocked WhatsApp targets by phone list or all."""
    own_session = db is None
    session = db or SessionLocal()
    try:
        deleted = 0
        if clear_all:
            rows = (
                session.query(Conversation)
                .filter(Conversation.id.like(f"{_WA_BLOCK_STATE_PREFIX}%"))
                .all()
            )
            for row in rows:
                session.delete(row)
                deleted += 1
        else:
            normalized = [_normalize_phone_br(phone) for phone in (phones or []) if _normalize_phone_br(phone)]
            for phone in normalized:
                record_id = _block_state_id(phone)
                row = session.query(Conversation).filter(Conversation.id == record_id).first()
                if row:
                    session.delete(row)
                    deleted += 1

        if deleted:
            session.commit()
        return deleted
    finally:
        if own_session:
            session.close()
