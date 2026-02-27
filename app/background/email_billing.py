"""
Billing Email Background Job

Runs daily receivable reminder campaign based on local financial records.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


async def daily_billing_email_job() -> Dict[str, Any]:
    """Execute one scheduled billing email campaign."""
    if not settings.EMAIL_BILLING_ENABLED:
        return {
            "success": True,
            "skipped": True,
            "reason": "EMAIL_BILLING_ENABLED is false",
        }

    logger.info(
        "Starting daily billing email campaign (provider=%s, dry_run=%s, real_send_enabled=%s)",
        settings.EMAIL_BILLING_PROVIDER,
        settings.EMAIL_BILLING_DRY_RUN,
        getattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False),
    )
    try:
        from app.services.email_billing_service import run_billing_email_campaign
    except Exception as exc:
        logger.error("Email billing module unavailable in this deployment: %s", exc)
        return {
            "success": False,
            "skipped": True,
            "reason": "email_billing_service module unavailable",
            "errors": [str(exc)],
        }

    result = await run_billing_email_campaign()

    if result.get("success"):
        logger.info(
            "Billing email campaign finished: sent=%s dry_run=%s failed=%s eligible_clients=%s",
            result.get("emails_sent"),
            result.get("emails_dry_run"),
            result.get("emails_failed"),
            result.get("eligible_clients"),
        )
    else:
        logger.error(
            "Billing email campaign finished with errors: %s",
            result.get("errors"),
        )

    return result
