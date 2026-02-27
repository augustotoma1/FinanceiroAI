"""
Contract Lifecycle Service

Monitors contract expiration windows and maintains status consistency.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.contract import Contract

MONITORED_STATUSES: Set[str] = {"active", "signed", "pending_signature"}
AUTO_EXPIRE_STATUSES: Set[str] = {"active", "signed"}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _add_months(base_date: date, months: int) -> date:
    """Return date with month offset while clamping day to target month."""
    month_index = base_date.month - 1 + max(int(months), 0)
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(base_date.day, last_day))


def resolve_contract_end_date(contract: Contract) -> Optional[date]:
    """Resolve effective end date from explicit end_date or duration/months."""
    if contract.end_date:
        return contract.end_date
    if contract.start_date and contract.duration_months and int(contract.duration_months) > 0:
        return _add_months(contract.start_date, int(contract.duration_months))
    return None


def _normalize_date(value: Optional[date]) -> date:
    if value:
        return value
    return datetime.now(timezone.utc).date()


def _days_until(end_date: date, *, today: date) -> int:
    return (end_date - today).days


def mark_expired_contracts(
    db: Session,
    *,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Auto-transition expired contracts (active/signed) to status='expired'.

    Returns summary with updated IDs and counters.
    """
    today = _normalize_date(reference_date)
    candidates = (
        db.query(Contract)
        .filter(Contract.status.in_(tuple(AUTO_EXPIRE_STATUSES)))
        .all()
    )

    updated_ids: List[int] = []
    for contract in candidates:
        end_date = resolve_contract_end_date(contract)
        if not end_date:
            continue
        if end_date < today:
            contract.status = "expired"
            updated_ids.append(int(contract.id))

    if updated_ids:
        db.commit()

    return {
        "updated_count": len(updated_ids),
        "updated_ids": updated_ids,
        "reference_date": today.isoformat(),
    }


def build_contract_lifecycle_snapshot(
    db: Session,
    *,
    reference_date: Optional[date] = None,
    days_ahead: int = 30,
) -> Dict[str, Any]:
    """Build contract lifecycle summary for dashboards and Telegram alerts."""
    today = _normalize_date(reference_date)
    window_days = max(int(days_ahead), 1)

    rows = (
        db.query(Contract, Client)
        .join(Client, Contract.client_id == Client.id)
        .all()
    )

    monitored_total = 0
    missing_end_date: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    expiring_soon: List[Dict[str, Any]] = []

    for contract, client in rows:
        status = _as_text(contract.status).lower()
        if status not in MONITORED_STATUSES:
            continue

        monitored_total += 1
        end_date = resolve_contract_end_date(contract)
        if not end_date:
            missing_end_date.append(
                {
                    "contract_id": int(contract.id),
                    "contract_number": _as_text(contract.contract_number),
                    "client_name": _as_text(client.name) or "Cliente",
                    "status": status,
                }
            )
            continue

        days_to_end = _days_until(end_date, today=today)
        payload = {
            "contract_id": int(contract.id),
            "contract_number": _as_text(contract.contract_number),
            "client_name": _as_text(client.name) or "Cliente",
            "status": status,
            "end_date": end_date.isoformat(),
            "days_to_end": days_to_end,
            "contract_value": float(contract.contract_value or 0.0),
        }

        if days_to_end < 0:
            overdue.append(payload)
        elif days_to_end <= window_days:
            expiring_soon.append(payload)

    overdue.sort(key=lambda item: item["days_to_end"])
    expiring_soon.sort(key=lambda item: item["days_to_end"])
    missing_end_date.sort(key=lambda item: item["contract_number"])

    return {
        "reference_date": today.isoformat(),
        "window_days": window_days,
        "monitored_total": monitored_total,
        "overdue_count": len(overdue),
        "expiring_soon_count": len(expiring_soon),
        "missing_end_date_count": len(missing_end_date),
        "overdue": overdue,
        "expiring_soon": expiring_soon,
        "missing_end_date": missing_end_date,
    }
