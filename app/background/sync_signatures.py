"""
Autentique Signature Synchronization Background Job

Periodically reconciles local contract/signature states with Autentique status.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import settings
from app.database import SessionLocal
from app.services.signature_sync_service import sync_signatures_from_autentique

logger = logging.getLogger(__name__)


async def sync_signatures_job(
    *,
    max_contracts: Optional[int] = None,
    only_open_contracts: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run one synchronization cycle against Autentique."""
    if not bool(getattr(settings, "AUTENTIQUE_SIGNATURE_SYNC_ENABLED", True)):
        return {
            "success": True,
            "skipped": True,
            "reason": "AUTENTIQUE_SIGNATURE_SYNC_ENABLED is false",
        }

    if not settings.AUTENTIQUE_API_KEY:
        return {
            "success": False,
            "skipped": True,
            "reason": "AUTENTIQUE_API_KEY not configured",
        }

    effective_max_contracts = (
        int(max_contracts)
        if max_contracts is not None
        else int(getattr(settings, "AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS", 100))
    )
    effective_only_open = (
        bool(only_open_contracts)
        if only_open_contracts is not None
        else bool(getattr(settings, "AUTENTIQUE_SIGNATURE_SYNC_ONLY_OPEN", True))
    )

    db = SessionLocal()
    try:
        logger.info(
            "Starting Autentique signature sync (max_contracts=%s, only_open=%s)",
            effective_max_contracts,
            effective_only_open,
        )
        result = await sync_signatures_from_autentique(
            db,
            max_contracts=effective_max_contracts,
            only_open_contracts=effective_only_open,
        )

        if result.get("success"):
            logger.info(
                "Autentique signature sync finished: processed=%s created=%s updated=%s updated_contracts=%s errors=%s",
                result.get("processed_contracts"),
                result.get("created_signatures"),
                result.get("updated_signatures"),
                result.get("updated_contracts"),
                result.get("error_count"),
            )
        else:
            logger.warning(
                "Autentique signature sync completed with issues: errors=%s first_error=%s",
                result.get("error_count"),
                (result.get("errors") or ["N/A"])[0],
            )
        return result
    finally:
        db.close()
