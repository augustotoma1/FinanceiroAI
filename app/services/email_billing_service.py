"""
Email Billing Service

Builds and sends daily receivable reminder emails with escalation levels.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.client import Client
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

_SUPPORTED_PROVIDERS = {"log", "sendgrid"}


class EmailBillingError(Exception):
    """Base exception for billing email failures."""


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
        logger.warning("Unknown EMAIL_BILLING_PROVIDER '%s'. Falling back to 'log'.", provider)
        return "log"
    return provider


def _parse_test_recipients(raw_value: Optional[str]) -> List[str]:
    """
    Parse and sanitize test recipient list from settings.
    Accepts comma/semicolon separated values.
    """
    raw = _as_text(raw_value)
    if not raw:
        return []

    normalized = raw.replace(";", ",")
    recipients: List[str] = []
    seen: set[str] = set()
    for chunk in normalized.split(","):
        email = _as_text(chunk).lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients


def _classify_escalation_level(
    *,
    due_date: date,
    today: date,
    due_soon_days: int,
    overdue_max_days: int,
) -> Optional[int]:
    """
    Classify escalation level for one receivable.

    Levels:
    - 1: due soon (0..due_soon_days)
    - 2: overdue (1..7 days)
    - 3: critical overdue (>=8 days)
    """
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


def _build_subject(level: int) -> str:
    if level == 3:
        return "AISATEC - Acao imediata: titulos em atraso"
    if level == 2:
        return "AISATEC - Aviso de cobranca: titulos em atraso"
    return "AISATEC - Lembrete de vencimento"


def _build_plain_body(reminder: Dict[str, Any]) -> str:
    lines = [
        f"Prezado(a) {reminder['client_name']},",
        "",
        "Segue o resumo financeiro da AISATEC:",
        "",
    ]
    for idx, item in enumerate(reminder["items"], 1):
        lines.append(
            f"{idx}. {item['transaction_number']} | {item['description']} | "
            f"vencimento: {item['due_date']} | valor: {_format_brl(item['amount'])}"
        )
    lines.extend(
        [
            "",
            f"Total em aberto: {_format_brl(reminder['total_amount'])}",
            "",
            "Caso ja tenha efetuado o pagamento, desconsidere esta mensagem.",
            "Em caso de duvidas, responda este email.",
            "",
            "Atenciosamente,",
            "Financeiro AISATEC",
        ]
    )
    return "\n".join(lines)


def _build_html_body(reminder: Dict[str, Any]) -> str:
    rows = []
    for item in reminder["items"]:
        rows.append(
            "<tr>"
            f"<td>{item['transaction_number']}</td>"
            f"<td>{item['description']}</td>"
            f"<td>{item['due_date']}</td>"
            f"<td>{_format_brl(item['amount'])}</td>"
            "</tr>"
        )
    rows_html = "".join(rows)
    return (
        "<html><body>"
        f"<p>Prezado(a) {reminder['client_name']},</p>"
        "<p>Segue o resumo financeiro da AISATEC:</p>"
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>"
        "<thead><tr>"
        "<th>Titulo</th><th>Descricao</th><th>Vencimento</th><th>Valor</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        f"<p><strong>Total em aberto:</strong> {_format_brl(reminder['total_amount'])}</p>"
        "<p>Caso ja tenha efetuado o pagamento, desconsidere esta mensagem.</p>"
        "<p>Atenciosamente,<br/>Financeiro AISATEC</p>"
        "</body></html>"
    )


def _collect_reminders(
    db: Session,
    *,
    today: date,
    due_soon_days: int,
    overdue_max_days: int,
    max_emails_per_run: int,
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
    skipped_missing_email = 0
    reminders_by_email: Dict[str, Dict[str, Any]] = {}

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

        client_email = _as_text(client.email).lower()
        if not client_email:
            skipped_missing_email += 1
            continue

        eligible_records += 1
        bucket = reminders_by_email.setdefault(
            client_email,
            {
                "client_name": _as_text(client.name) or "Cliente",
                "to_email": client_email,
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
                "description": _as_text(financial.description) or "Sem descricao",
                "due_date": financial.due_date.isoformat(),
                "amount": amount,
            }
        )

    reminders = list(reminders_by_email.values())
    for reminder in reminders:
        reminder["items"] = sorted(reminder["items"], key=lambda item: item["due_date"])

    reminders = sorted(
        reminders,
        key=lambda reminder: (-int(reminder["level"]), -float(reminder["total_amount"])),
    )[: max(1, max_emails_per_run)]

    level_counts = {"1": 0, "2": 0, "3": 0}
    for reminder in reminders:
        level_counts[str(reminder["level"])] += 1

    return {
        "reminders": reminders,
        "evaluated_records": evaluated_records,
        "eligible_records": eligible_records,
        "eligible_clients": len(reminders),
        "skipped_missing_email": skipped_missing_email,
        "level_counts": level_counts,
    }


async def _dispatch_sendgrid_email(
    *,
    to_email: str,
    to_name: str,
    subject: str,
    plain_text: str,
    html_content: str,
) -> None:
    api_key = _as_text(settings.SENDGRID_API_KEY)
    from_email = _as_text(settings.EMAIL_BILLING_FROM)
    if not api_key or not from_email:
        raise EmailBillingError("Missing SENDGRID_API_KEY or EMAIL_BILLING_FROM")

    payload: Dict[str, Any] = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name or "Cliente"}]}],
        "from": {"email": from_email, "name": "Financeiro AISATEC"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_text},
            {"type": "text/html", "value": html_content},
        ],
    }
    reply_to = _as_text(settings.EMAIL_BILLING_REPLY_TO)
    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 300:
        snippet = _as_text(response.text)[:250]
        raise EmailBillingError(
            f"SendGrid send failed ({response.status_code}): {snippet}"
        )


async def run_billing_email_campaign(
    *,
    db: Optional[Session] = None,
    today: Optional[date] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Execute one billing email campaign pass.

    This function is safe to run in scheduler and on-demand calls.
    """
    started_at = datetime.now(timezone.utc)
    own_session = db is None
    session = db or SessionLocal()
    errors: List[str] = []

    provider = _normalize_provider(settings.EMAIL_BILLING_PROVIDER)
    effective_dry_run = settings.EMAIL_BILLING_DRY_RUN if dry_run is None else bool(dry_run)
    real_send_enabled = bool(getattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False))
    test_recipients = _parse_test_recipients(settings.EMAIL_BILLING_TEST_RECIPIENTS)
    run_date = today or datetime.now(timezone.utc).date()
    due_soon_days = max(int(settings.EMAIL_BILLING_DUE_SOON_DAYS), 0)
    overdue_max_days = max(int(settings.EMAIL_BILLING_OVERDUE_MAX_DAYS), 1)
    max_emails_per_run = max(int(settings.EMAIL_BILLING_MAX_EMAILS_PER_RUN), 1)

    emails_sent = 0
    emails_dry_run = 0
    emails_failed = 0
    targets_preview: List[Dict[str, Any]] = []

    try:
        summary = _collect_reminders(
            session,
            today=run_date,
            due_soon_days=due_soon_days,
            overdue_max_days=overdue_max_days,
            max_emails_per_run=max_emails_per_run,
        )
        reminders = summary["reminders"]

        send_enabled = provider == "sendgrid" and not effective_dry_run and real_send_enabled
        if provider == "sendgrid" and send_enabled:
            if not _as_text(settings.SENDGRID_API_KEY) or not _as_text(settings.EMAIL_BILLING_FROM):
                errors.append("Missing SENDGRID_API_KEY or EMAIL_BILLING_FROM for sendgrid provider.")
                send_enabled = False

        for reminder in reminders:
            original_to = _as_text(reminder["to_email"]).lower()
            items = list(reminder.get("items") or [])
            first_due = _as_text(items[0].get("due_date")) if items else ""
            last_due = _as_text(items[-1].get("due_date")) if items else ""
            targets_preview.append(
                {
                    "client_name": _as_text(reminder.get("client_name")) or "Cliente",
                    "to_email": original_to,
                    "level": int(reminder.get("level") or 1),
                    "total_amount": float(reminder.get("total_amount") or 0.0),
                    "items_count": len(items),
                    "first_due_date": first_due,
                    "last_due_date": last_due,
                }
            )

            subject = _build_subject(int(reminder["level"]))
            plain = _build_plain_body(reminder)
            html = _build_html_body(reminder)

            dispatch_targets = [original_to]
            if test_recipients:
                dispatch_targets = test_recipients
                subject = f"[TESTE] {subject}"
                plain += (
                    "\n\n---\n"
                    "MODO TESTE ATIVO\n"
                    f"Destinatario real bloqueado: {original_to}\n"
                )
                html += (
                    "<p><strong>MODO TESTE ATIVO</strong><br/>"
                    f"Destinatario real bloqueado: {original_to}</p>"
                )

            for target_email in dispatch_targets:
                if not send_enabled:
                    emails_dry_run += 1
                    logger.info(
                        "[email-billing dry-run] to=%s original_to=%s level=%s total=%s items=%s",
                        target_email,
                        original_to,
                        reminder["level"],
                        _format_brl(float(reminder["total_amount"])),
                        len(reminder["items"]),
                    )
                    continue

                try:
                    await _dispatch_sendgrid_email(
                        to_email=target_email,
                        to_name=reminder["client_name"],
                        subject=subject,
                        plain_text=plain,
                        html_content=html,
                    )
                    emails_sent += 1
                except Exception as exc:  # pragma: no cover - defensive guard
                    emails_failed += 1
                    error_message = (
                        f"Failed email to {target_email} (original {original_to}): {exc}"
                    )
                    errors.append(error_message)
                    logger.error(error_message)

        success = len(errors) == 0
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        return {
            "success": success,
            "provider": provider,
            "dry_run": not send_enabled,
            "real_send_enabled": real_send_enabled,
            "evaluated_records": summary["evaluated_records"],
            "eligible_records": summary["eligible_records"],
            "eligible_clients": summary["eligible_clients"],
            "skipped_missing_email": summary["skipped_missing_email"],
            "level_counts": summary["level_counts"],
            "emails_sent": emails_sent,
            "emails_dry_run": emails_dry_run,
            "emails_failed": emails_failed,
            "test_mode": bool(test_recipients),
            "test_recipients": test_recipients,
            "targets_preview": targets_preview,
            "errors": errors,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    finally:
        if own_session:
            session.close()
