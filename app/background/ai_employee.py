"""
AI Employee background job.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.agents.orchestrator import AIEmployeeOrchestrator
from app.config import settings

logger = logging.getLogger(__name__)


async def daily_ai_employee_job() -> Dict[str, Any]:
    """
    Execute one scheduled AI Employee cycle.
    """
    if not bool(getattr(settings, "AI_EMPLOYEE_ENABLED", False)):
        return {
            "success": True,
            "skipped": True,
            "reason": "AI_EMPLOYEE_ENABLED is false",
        }

    orchestrator = AIEmployeeOrchestrator()
    result = await orchestrator.run_daily_operations(trigger="scheduler")

    if result.get("success"):
        summary = result.get("summary") or {}
        cfo = summary.get("cfo_assistant") or {}
        logger.info(
            "AI Employee cycle finished (engine=%s dry_run=%s risk=%s projected_15d=%s)",
            result.get("mode"),
            result.get("dry_run"),
            cfo.get("risk_level"),
            cfo.get("projected_15d"),
        )
    elif result.get("skipped"):
        logger.info("AI Employee cycle skipped: %s", result.get("reason"))
    else:
        logger.warning(
            "AI Employee cycle finished with errors: %s",
            result.get("errors"),
        )

    return result
