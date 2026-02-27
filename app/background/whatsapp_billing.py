"""
WhatsApp Billing Background Job

Runs daily receivable reminder campaign through WhatsApp provider.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


async def daily_whatsapp_billing_job() -> Dict[str, Any]:
    """Execute one scheduled WhatsApp billing campaign."""
    if not bool(getattr(settings, "WHATSAPP_FEATURE_ENABLED", False)):
        return {
            "success": True,
            "skipped": True,
            "reason": "WHATSAPP_FEATURE_ENABLED is false (phase disabled)",
        }

    if not settings.WHATSAPP_BILLING_ENABLED:
        return {
            "success": True,
            "skipped": True,
            "reason": "WHATSAPP_BILLING_ENABLED is false",
        }

    configured_dry_run = bool(getattr(settings, "WHATSAPP_BILLING_DRY_RUN", True))
    require_confirmation = bool(getattr(settings, "WHATSAPP_BILLING_REQUIRE_CONFIRMATION", True))
    effective_dry_run = configured_dry_run or require_confirmation

    logger.info(
        "Starting daily WhatsApp billing campaign (provider=%s, configured_dry_run=%s, require_confirmation=%s, effective_dry_run=%s)",
        settings.WHATSAPP_BILLING_PROVIDER,
        configured_dry_run,
        require_confirmation,
        effective_dry_run,
    )
    if require_confirmation and not configured_dry_run:
        logger.warning(
            "WHATSAPP_BILLING_REQUIRE_CONFIRMATION=true active: scheduled campaign forced to dry-run preview."
        )

    try:
        from app.services.whatsapp_billing_service import run_whatsapp_billing_campaign
    except Exception as exc:
        logger.error("WhatsApp billing module unavailable in this deployment: %s", exc)
        return {
            "success": False,
            "skipped": True,
            "reason": "whatsapp_billing_service module unavailable",
            "errors": [str(exc)],
        }

    result = await run_whatsapp_billing_campaign(dry_run=effective_dry_run)
    result["forced_dry_run"] = bool(require_confirmation and not configured_dry_run)

    if result.get("success"):
        logger.info(
            "WhatsApp billing campaign finished: sent=%s dry_run=%s failed=%s eligible_clients=%s blocked=%s",
            result.get("messages_sent"),
            result.get("messages_dry_run"),
            result.get("messages_failed"),
            result.get("eligible_clients"),
            result.get("skipped_blocked_phone"),
        )
    else:
        logger.error(
            "WhatsApp billing campaign finished with errors: %s",
            result.get("errors"),
        )

    return result
