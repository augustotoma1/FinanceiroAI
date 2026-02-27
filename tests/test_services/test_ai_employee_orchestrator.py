"""
Tests for AI Employee orchestrator.
"""

import pytest
from unittest.mock import AsyncMock

import app.agents.orchestrator as orchestrator_module
from app.agents.orchestrator import AIEmployeeOrchestrator
from app.config import settings


class _FakeTools:
    async def get_client_sync_health(self):
        return {
            "total_clients": 201,
            "synced_clients": 201,
            "sync_freshness": "fresh",
            "hours_since_last_sync": 0.3,
        }

    async def get_financial_sync_health(self):
        return {
            "total_records": 1131,
            "receivable_records": 595,
            "payable_records": 536,
            "overdue_records": 147,
            "last_sync_time": "2026-02-16T13:49:39+00:00",
        }

    async def get_cash_risk_overview(self, *, force_refresh=False):
        _ = force_refresh
        return {
            "snapshot": {
                "risk_level": "medio",
                "projected_15d": 59981.98,
                "top3_concentration_pct": 70.3,
            },
            "trend": {"direction": "stable"},
        }

    async def get_contract_lifecycle_overview(self, *, days_ahead=30):
        _ = days_ahead
        return {
            "monitored_total": 1,
            "expiring_soon_count": 1,
            "overdue_count": 0,
            "missing_end_date_count": 0,
        }

    async def preview_email_billing(self):
        return {
            "eligible_clients": 17,
            "eligible_records": 19,
            "success": True,
        }

    async def preview_whatsapp_billing(self):
        return {
            "eligible_clients": 0,
            "eligible_records": 0,
            "success": True,
            "skipped": True,
            "reason": "feature disabled",
        }

    async def log_agent_action(self, **kwargs):
        _ = kwargs
        return {"logged": True}


@pytest.mark.asyncio
async def test_run_daily_operations_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", False)
    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())

    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is True
    assert result["skipped"] is True
    assert "AI_EMPLOYEE_ENABLED is false" in result["reason"]


@pytest.mark.asyncio
async def test_run_daily_operations_builtin_success(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "builtin")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())

    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is True
    assert result["mode"] == "builtin"
    assert result["dry_run"] is True
    assert "summary" in result
    assert result["summary"]["cfo_assistant"]["risk_level"] == "medio"
    assert result["summary"]["cobrador"]["eligible_email_clients"] == 17
    assert len(result["actions"]) >= 3
    assert result["errors"] == []


def test_runtime_status_exposes_feature_flags(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "builtin")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_EXECUTION_ENABLED", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DAILY_SUMMARY_ENABLED", False)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda _module_name: False)
    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())

    status = orchestrator.runtime_status()

    assert status["enabled"] is True
    assert status["dry_run"] is True
    assert status["requested_engine"] == "builtin"
    assert status["runtime_engine"] == "builtin"
    assert status["engine_degraded"] is False
    assert "auto" in status["supported_engines"]
    assert status["crewai_execution_enabled"] is False


def test_crewai_engine_falls_back_when_feature_flag_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "crewai")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", False)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda module_name: module_name == "crewai")

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())

    assert orchestrator.requested_engine == "crewai"
    assert orchestrator.runtime_engine == "builtin"
    status = orchestrator.runtime_status()
    assert status["engine_degraded"] is True
    assert "AI_EMPLOYEE_CREW_ENABLED" in status["runtime_reason"]


@pytest.mark.asyncio
async def test_run_daily_operations_crewai_compat_mode(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "crewai")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_EXECUTION_ENABLED", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda module_name: module_name == "crewai")

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is True
    assert result["mode"] == "crewai"
    assert result["crew"]["runtime"] == "planning_only"
    assert [item["name"] for item in result["crew"]["agents"]] == ["cobrador", "contratos", "analista_cfo"]
    assert result["runtime_status"]["runtime_engine"] == "crewai"
    assert result["crew"]["execution_enabled"] is False


@pytest.mark.asyncio
async def test_run_daily_operations_langgraph_branch(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "langgraph")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda module_name: module_name == "langgraph")

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    orchestrator._run_langgraph_flow = AsyncMock(return_value={  # type: ignore[method-assign]
        "success": True,
        "mode": "langgraph",
        "dry_run": True,
        "actions": [],
        "summary": {},
        "errors": [],
    })

    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is True
    assert result["mode"] == "langgraph"
    assert result["runtime_status"]["runtime_engine"] == "langgraph"


def test_auto_engine_prefers_langgraph(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "auto")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", True)
    monkeypatch.setattr(
        orchestrator_module,
        "_module_available",
        lambda module_name: module_name == "langgraph",
    )

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    status = orchestrator.runtime_status()

    assert orchestrator.runtime_engine == "langgraph"
    assert status["requested_engine"] == "auto"
    assert status["runtime_reason"] == "auto_selected_langgraph"
    assert status["engine_degraded"] is False


def test_auto_engine_uses_crewai_when_langgraph_missing(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "auto")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", True)
    monkeypatch.setattr(
        orchestrator_module,
        "_module_available",
        lambda module_name: module_name == "crewai",
    )

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    status = orchestrator.runtime_status()

    assert orchestrator.runtime_engine == "crewai"
    assert status["requested_engine"] == "auto"
    assert status["runtime_reason"] == "auto_selected_crewai"
    assert status["engine_degraded"] is False


@pytest.mark.asyncio
async def test_run_daily_operations_allows_engine_override(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "builtin")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda _module_name: False)

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    orchestrator._run_builtin_flow = AsyncMock(return_value={  # type: ignore[method-assign]
        "success": True,
        "mode": "builtin",
        "dry_run": True,
        "actions": [],
        "summary": {},
        "errors": [],
    })

    result = await orchestrator.run_daily_operations(trigger="test", engine_override="langgraph")

    assert result["success"] is True
    assert result["mode"] == "builtin"
    assert result["runtime_status"]["requested_engine"] == "langgraph"
    assert result["runtime_status"]["runtime_engine"] == "builtin"
    assert result["runtime_status"]["engine_degraded"] is True


@pytest.mark.asyncio
async def test_run_daily_operations_crewai_native_execution(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "crewai")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda module_name: module_name == "crewai")

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    orchestrator._run_crewai_native = AsyncMock(return_value={  # type: ignore[method-assign]
        "runtime": "native",
        "output_preview": "briefing",
    })

    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is True
    assert result["mode"] == "crewai"
    assert result["crew"]["execution_enabled"] is True
    assert result["crew"]["runtime"] == "native"
    assert result["crew"]["output_preview"] == "briefing"


@pytest.mark.asyncio
async def test_run_daily_operations_crewai_native_failure_marks_run_error(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_DRY_RUN", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "crewai")
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_CREW_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW", True)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW", False)
    monkeypatch.setattr(settings, "AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(orchestrator_module, "_module_available", lambda module_name: module_name == "crewai")

    orchestrator = AIEmployeeOrchestrator(tools=_FakeTools())
    orchestrator._run_crewai_native = AsyncMock(return_value={  # type: ignore[method-assign]
        "runtime": "native_failed",
        "error": "llm_unavailable",
    })

    result = await orchestrator.run_daily_operations(trigger="test")

    assert result["success"] is False
    assert any("crewai_native:llm_unavailable" == item for item in result["errors"])
