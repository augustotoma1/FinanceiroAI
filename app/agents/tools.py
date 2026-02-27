"""
Tool wrapper layer for AI Employee orchestration.

This module centralizes side effects and integrations used by orchestrators.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from app.config import settings
from app.database import SessionLocal
from app.models.conversation import Conversation
from app.services.contract_lifecycle_service import build_contract_lifecycle_snapshot

logger = logging.getLogger(__name__)


class AIEmployeeTools:
    """Reusable integration wrappers for Cobrador, Contratos and CFO agents."""

    async def get_client_sync_health(self) -> Dict[str, Any]:
        from app.background.sync_clients import get_sync_status

        return await get_sync_status()

    async def get_financial_sync_health(self) -> Dict[str, Any]:
        from app.background.sync_financial import get_financial_sync_status

        return await get_financial_sync_status()

    async def get_cash_risk_overview(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        from app.services.cash_risk_service import get_cash_risk_dashboard_data

        db = SessionLocal()
        try:
            return await get_cash_risk_dashboard_data(
                db=db,
                force_refresh=force_refresh,
                history_days=30,
            )
        finally:
            db.close()

    async def get_contract_lifecycle_overview(self, *, days_ahead: int = 30) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            return build_contract_lifecycle_snapshot(db, days_ahead=max(1, min(days_ahead, 365)))
        finally:
            db.close()

    async def preview_email_billing(self) -> Dict[str, Any]:
        if not bool(getattr(settings, "EMAIL_BILLING_ENABLED", False)):
            return {
                "success": True,
                "skipped": True,
                "reason": "EMAIL_BILLING_ENABLED is false",
            }

        from app.services.email_billing_service import run_billing_email_campaign

        return await run_billing_email_campaign(dry_run=True)

    async def preview_whatsapp_billing(self) -> Dict[str, Any]:
        if not bool(getattr(settings, "WHATSAPP_FEATURE_ENABLED", False)):
            return {
                "success": True,
                "skipped": True,
                "reason": "WHATSAPP_FEATURE_ENABLED is false",
            }
        if not bool(getattr(settings, "WHATSAPP_BILLING_ENABLED", False)):
            return {
                "success": True,
                "skipped": True,
                "reason": "WHATSAPP_BILLING_ENABLED is false",
            }

        from app.services.whatsapp_billing_service import run_whatsapp_billing_campaign

        return await run_whatsapp_billing_campaign(dry_run=True)

    async def log_agent_action(
        self,
        *,
        agent: str,
        action: str,
        payload: Dict[str, Any],
        status: str = "ok",
    ) -> Dict[str, Any]:
        """
        Persist one agent action event in Conversation table for auditability.
        """
        if not bool(getattr(settings, "AI_EMPLOYEE_LOG_ACTIONS", True)):
            return {"logged": False, "reason": "AI_EMPLOYEE_LOG_ACTIONS is false"}

        db = SessionLocal()
        try:
            event_id = str(uuid4())
            record = Conversation(
                id=event_id,
                messages=[],
                complete=True,
                data={
                    "kind": "ai_employee_action",
                    "agent": str(agent),
                    "action": str(action),
                    "status": str(status),
                    "payload": payload,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.add(record)
            db.commit()
            return {"logged": True, "event_id": event_id}
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist AI Employee action log: %s", exc, exc_info=True)
            return {"logged": False, "reason": str(exc)}
        finally:
            db.close()
