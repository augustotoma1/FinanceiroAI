"""
Contract Lifecycle Background Job

Runs daily status maintenance and lifecycle summary generation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings
from app.database import SessionLocal
from app.services.contract_lifecycle_service import (
    build_contract_lifecycle_snapshot,
    mark_expired_contracts,
)

logger = logging.getLogger(__name__)


async def daily_contract_lifecycle_job() -> Dict[str, Any]:
    """Execute daily contract lifecycle maintenance."""
    if not bool(getattr(settings, "CONTRACT_LIFECYCLE_ENABLED", True)):
        return {
            "success": True,
            "skipped": True,
            "reason": "CONTRACT_LIFECYCLE_ENABLED is false",
        }

    session = SessionLocal()
    try:
        maintenance = mark_expired_contracts(session)
        snapshot = build_contract_lifecycle_snapshot(
            session,
            days_ahead=int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30)),
        )
        result: Dict[str, Any] = {
            "success": True,
            "updated_count": maintenance["updated_count"],
            "reference_date": maintenance["reference_date"],
            "expiring_soon_count": snapshot["expiring_soon_count"],
            "overdue_count": snapshot["overdue_count"],
            "missing_end_date_count": snapshot["missing_end_date_count"],
        }
        logger.info(
            "Contract lifecycle job finished: updated=%s expiring=%s overdue=%s missing_end=%s",
            result["updated_count"],
            result["expiring_soon_count"],
            result["overdue_count"],
            result["missing_end_date_count"],
        )
        return result
    except Exception as exc:
        session.rollback()
        logger.error("Contract lifecycle job failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "error": str(exc),
        }
    finally:
        session.close()
