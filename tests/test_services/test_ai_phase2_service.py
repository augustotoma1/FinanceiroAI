"""
Tests for AI phase2 readiness service.
"""

from app.services.ai_phase2_service import evaluate_phase2_levels


def test_evaluate_phase2_levels_ready_path():
    runtime_status = {"enabled": True, "dry_run": False}
    data_health = {
        "client_sync_available": True,
        "financial_sync_available": True,
        "cash_risk_available": True,
        "contract_lifecycle_available": True,
    }
    communication_health = {
        "telegram_channel_available": True,
        "email_channel_available": True,
        "whatsapp_channel_available": False,
    }

    result = evaluate_phase2_levels(
        runtime_status=runtime_status,
        data_health=data_health,
        communication_health=communication_health,
    )

    assert result["level_1_validation"]["status"] == "ready"
    assert result["level_2_communication"]["status"] == "ready"
    assert result["level_3_decision_support"]["status"] == "ready"
    assert result["next_steps"] == []


def test_evaluate_phase2_levels_blocked_when_core_dependencies_missing():
    runtime_status = {"enabled": False, "dry_run": True}
    data_health = {
        "client_sync_available": False,
        "financial_sync_available": False,
        "cash_risk_available": False,
        "contract_lifecycle_available": False,
    }
    communication_health = {
        "telegram_channel_available": False,
        "email_channel_available": False,
        "whatsapp_channel_available": False,
    }

    result = evaluate_phase2_levels(
        runtime_status=runtime_status,
        data_health=data_health,
        communication_health=communication_health,
    )

    assert result["level_1_validation"]["status"] == "blocked"
    assert result["level_2_communication"]["status"] == "blocked"
    assert result["level_3_decision_support"]["status"] == "blocked"
    assert len(result["next_steps"]) >= 2
