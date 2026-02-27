"""
Phase 2 AI readiness service.

Provides an objective readiness snapshot for the 3 rollout levels:
1) validation, 2) client communication, 3) decision support.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.agents.orchestrator import AIEmployeeOrchestrator
from app.agents.tools import AIEmployeeTools
from app.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any) -> bool:
    return bool(value)


def evaluate_phase2_levels(
    *,
    runtime_status: Dict[str, Any],
    data_health: Dict[str, bool],
    communication_health: Dict[str, bool],
) -> Dict[str, Any]:
    """Evaluate readiness status for the 3 phase-2 levels."""
    level_1_checks = {
        "client_sync_available": _safe_bool(data_health.get("client_sync_available")),
        "financial_sync_available": _safe_bool(data_health.get("financial_sync_available")),
        "cash_risk_available": _safe_bool(data_health.get("cash_risk_available")),
        "contract_lifecycle_available": _safe_bool(data_health.get("contract_lifecycle_available")),
    }
    level_1_ok = sum(1 for ok in level_1_checks.values() if ok)
    if level_1_ok == len(level_1_checks):
        level_1_status = "ready"
    elif level_1_ok == 0:
        level_1_status = "blocked"
    else:
        level_1_status = "partial"

    level_2_checks = {
        "telegram_channel_available": _safe_bool(communication_health.get("telegram_channel_available")),
        "email_channel_available": _safe_bool(communication_health.get("email_channel_available")),
        "whatsapp_channel_available": _safe_bool(communication_health.get("whatsapp_channel_available")),
    }
    level_2_status = "ready"
    if not level_2_checks["telegram_channel_available"]:
        level_2_status = "blocked"
    elif not (
        level_2_checks["email_channel_available"] or level_2_checks["whatsapp_channel_available"]
    ):
        level_2_status = "partial"

    ai_enabled = _safe_bool(runtime_status.get("enabled"))
    dry_run = _safe_bool(runtime_status.get("dry_run"))
    logging_enabled = _safe_bool(getattr(settings, "AI_EMPLOYEE_LOG_ACTIONS", True))
    level_3_checks = {
        "ai_employee_enabled": ai_enabled,
        "action_logging_enabled": logging_enabled,
        "validation_layer_operational": level_1_status in {"ready", "partial"},
        "communication_layer_operational": level_2_status in {"ready", "partial"},
    }
    if not ai_enabled or not logging_enabled:
        level_3_status = "blocked"
    elif dry_run:
        level_3_status = "partial"
    else:
        level_3_status = "ready"

    next_steps: List[str] = []
    if level_1_status != "ready":
        next_steps.append("Estabilizar integrações de dados (clientes, financeiro, risco e contratos).")
    if level_2_status != "ready":
        next_steps.append("Habilitar canais de comunicação (Telegram + e-mail/WhatsApp) com política de envio.")
    if level_3_status != "ready":
        next_steps.append("Sair de dry-run e formalizar aprovação operacional para apoio à decisão.")

    return {
        "level_1_validation": {"status": level_1_status, "checks": level_1_checks},
        "level_2_communication": {"status": level_2_status, "checks": level_2_checks},
        "level_3_decision_support": {"status": level_3_status, "checks": level_3_checks},
        "next_steps": next_steps,
    }


async def _safe_collect(label: str, coro: Any) -> Tuple[bool, Dict[str, Any]]:
    try:
        payload = await coro
        return True, {"label": label, "ok": True, "payload": payload}
    except Exception as exc:
        return False, {"label": label, "ok": False, "error": str(exc)}


async def get_phase2_readiness_snapshot() -> Dict[str, Any]:
    """Build live readiness snapshot for Phase 2 rollout."""
    orchestrator = AIEmployeeOrchestrator()
    tools = AIEmployeeTools()
    runtime_status = orchestrator.runtime_status()

    client_ok, client_meta = await _safe_collect("client_sync", tools.get_client_sync_health())
    financial_ok, financial_meta = await _safe_collect(
        "financial_sync", tools.get_financial_sync_health()
    )
    cash_ok, cash_meta = await _safe_collect(
        "cash_risk", tools.get_cash_risk_overview(force_refresh=False)
    )
    contracts_ok, contracts_meta = await _safe_collect(
        "contract_lifecycle", tools.get_contract_lifecycle_overview(days_ahead=30)
    )

    email_enabled = _safe_bool(getattr(settings, "EMAIL_BILLING_ENABLED", False))
    whatsapp_enabled = _safe_bool(
        getattr(settings, "WHATSAPP_FEATURE_ENABLED", False)
        and getattr(settings, "WHATSAPP_BILLING_ENABLED", False)
    )
    telegram_enabled = _safe_bool(getattr(settings, "TELEGRAM_BOT_TOKEN", ""))

    email_ok = True
    email_meta: Dict[str, Any] = {"label": "email_billing", "ok": True, "skipped": True}
    if email_enabled:
        email_ok, email_meta = await _safe_collect("email_billing", tools.preview_email_billing())

    whatsapp_ok = True
    whatsapp_meta: Dict[str, Any] = {"label": "whatsapp_billing", "ok": True, "skipped": True}
    if whatsapp_enabled:
        whatsapp_ok, whatsapp_meta = await _safe_collect(
            "whatsapp_billing", tools.preview_whatsapp_billing()
        )

    data_health = {
        "client_sync_available": client_ok,
        "financial_sync_available": financial_ok,
        "cash_risk_available": cash_ok,
        "contract_lifecycle_available": contracts_ok,
    }
    communication_health = {
        "telegram_channel_available": telegram_enabled,
        "email_channel_available": email_enabled and email_ok,
        "whatsapp_channel_available": whatsapp_enabled and whatsapp_ok,
    }

    levels = evaluate_phase2_levels(
        runtime_status=runtime_status,
        data_health=data_health,
        communication_health=communication_health,
    )

    return {
        "generated_at": _utc_now_iso(),
        "runtime_status": runtime_status,
        "feature_flags": {
            "email_billing_enabled": email_enabled,
            "whatsapp_billing_enabled": whatsapp_enabled,
            "telegram_alerts_enabled": telegram_enabled,
            "ai_employee_daily_summary_enabled": _safe_bool(
                getattr(settings, "AI_EMPLOYEE_DAILY_SUMMARY_ENABLED", False)
            ),
        },
        "integration_probes": {
            "client_sync": client_meta,
            "financial_sync": financial_meta,
            "cash_risk": cash_meta,
            "contract_lifecycle": contracts_meta,
            "email_billing": email_meta,
            "whatsapp_billing": whatsapp_meta,
        },
        **levels,
    }
