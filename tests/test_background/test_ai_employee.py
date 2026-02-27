"""
Tests for AI Employee background job.
"""

import pytest

import app.background.ai_employee as ai_employee_bg
from app.config import settings


@pytest.mark.asyncio
async def test_daily_ai_employee_job_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", False)

    result = await ai_employee_bg.daily_ai_employee_job()

    assert result["success"] is True
    assert result["skipped"] is True
    assert "AI_EMPLOYEE_ENABLED is false" in result["reason"]


@pytest.mark.asyncio
async def test_daily_ai_employee_job_executes_orchestrator(monkeypatch):
    monkeypatch.setattr(settings, "AI_EMPLOYEE_ENABLED", True)

    class _FakeOrchestrator:
        async def run_daily_operations(self, *, trigger="manual", force=False):
            return {
                "success": True,
                "mode": "builtin",
                "dry_run": True,
                "trigger": trigger,
                "summary": {"cfo_assistant": {"risk_level": "medio", "projected_15d": 1000.0}},
                "actions": [],
                "errors": [],
            }

    monkeypatch.setattr(ai_employee_bg, "AIEmployeeOrchestrator", _FakeOrchestrator)

    result = await ai_employee_bg.daily_ai_employee_job()

    assert result["success"] is True
    assert result["trigger"] == "scheduler"
    assert result["summary"]["cfo_assistant"]["risk_level"] == "medio"
