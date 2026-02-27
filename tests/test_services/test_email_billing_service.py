"""
Unit tests for billing email campaign service.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.client import Client
from app.models.financial_record import FinancialRecord
from app.services.email_billing_service import (
    _classify_escalation_level,
    run_billing_email_campaign,
)


def _create_client(db_session, *, name: str, cpf_cnpj: str, email: str | None) -> Client:
    client = Client(
        name=name,
        cpf_cnpj=cpf_cnpj,
        email=email,
    )
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


def _create_receivable(
    db_session,
    *,
    client_id: int,
    transaction_number: str,
    due_date: date,
    amount: float,
    status: str = "pending",
) -> FinancialRecord:
    record = FinancialRecord(
        client_id=client_id,
        transaction_type="receivable",
        transaction_number=transaction_number,
        description=f"Titulo {transaction_number}",
        amount=amount,
        currency="BRL",
        status=status,
        transaction_date=due_date - timedelta(days=15),
        due_date=due_date,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_classify_escalation_level():
    """Escalation level should follow due-soon and overdue windows."""
    today = date(2026, 2, 15)

    assert (
        _classify_escalation_level(
            due_date=today + timedelta(days=2),
            today=today,
            due_soon_days=3,
            overdue_max_days=30,
        )
        == 1
    )
    assert (
        _classify_escalation_level(
            due_date=today - timedelta(days=3),
            today=today,
            due_soon_days=3,
            overdue_max_days=30,
        )
        == 2
    )
    assert (
        _classify_escalation_level(
            due_date=today - timedelta(days=12),
            today=today,
            due_soon_days=3,
            overdue_max_days=30,
        )
        == 3
    )
    assert (
        _classify_escalation_level(
            due_date=today + timedelta(days=8),
            today=today,
            due_soon_days=3,
            overdue_max_days=30,
        )
        is None
    )


@pytest.mark.asyncio
async def test_campaign_dry_run_groups_by_client_and_highest_level(db_session, monkeypatch):
    """Dry-run campaign should aggregate by client and pick highest urgency level."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente A",
        cpf_cnpj="12345678901",
        email="cliente.a@example.com",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-001",
        due_date=today + timedelta(days=1),
        amount=250.0,
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-002",
        due_date=today - timedelta(days=10),
        amount=500.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "EMAIL_BILLING_PROVIDER", "log", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_TEST_RECIPIENTS", "", raising=False)
    result = await run_billing_email_campaign(db=db_session, today=today, dry_run=True)

    assert result["success"] is True
    assert result["eligible_clients"] == 1
    assert result["eligible_records"] == 2
    assert result["emails_dry_run"] == 1
    assert result["emails_sent"] == 0
    assert result["level_counts"]["3"] == 1


@pytest.mark.asyncio
async def test_campaign_skips_records_without_client_email(db_session, monkeypatch):
    """Records without client email must be counted as skipped and not sent."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente Sem Email",
        cpf_cnpj="10987654321",
        email=None,
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-003",
        due_date=today - timedelta(days=2),
        amount=400.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "EMAIL_BILLING_PROVIDER", "log", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_TEST_RECIPIENTS", "", raising=False)
    result = await run_billing_email_campaign(db=db_session, today=today, dry_run=True)

    assert result["success"] is True
    assert result["eligible_clients"] == 0
    assert result["emails_dry_run"] == 0
    assert result["skipped_missing_email"] == 1


@pytest.mark.asyncio
async def test_campaign_sendgrid_dispatch_success(db_session, monkeypatch):
    """When provider is sendgrid and dry_run is false, dispatch should be awaited."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente Sendgrid",
        cpf_cnpj="99999999999",
        email="cobranca@example.com",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-004",
        due_date=today - timedelta(days=1),
        amount=100.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "EMAIL_BILLING_PROVIDER", "sendgrid", raising=False)
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "sg-test-key", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_FROM", "financeiro@aisatec.com.br", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_TEST_RECIPIENTS", "", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", True, raising=False)

    with patch(
        "app.services.email_billing_service._dispatch_sendgrid_email",
        new=AsyncMock(return_value=None),
    ) as mock_dispatch:
        result = await run_billing_email_campaign(db=db_session, today=today, dry_run=False)

    assert result["success"] is True
    assert result["emails_sent"] == 1
    assert result["emails_failed"] == 0
    assert mock_dispatch.await_count == 1


@pytest.mark.asyncio
async def test_campaign_sendgrid_redirects_to_test_recipients(db_session, monkeypatch):
    """When test recipients are configured, real client emails must be bypassed."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente Real",
        cpf_cnpj="11122233344",
        email="cliente.real@example.com",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-TEST-EMAIL",
        due_date=today - timedelta(days=1),
        amount=150.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "EMAIL_BILLING_PROVIDER", "sendgrid", raising=False)
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "sg-test-key", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_FROM", "financeiro@aisatec.com.br", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", True, raising=False)
    monkeypatch.setattr(
        settings,
        "EMAIL_BILLING_TEST_RECIPIENTS",
        "augusto@satec.digital,augusto+teste@satec.digital",
        raising=False,
    )

    with patch(
        "app.services.email_billing_service._dispatch_sendgrid_email",
        new=AsyncMock(return_value=None),
    ) as mock_dispatch:
        result = await run_billing_email_campaign(db=db_session, today=today, dry_run=False)

    assert result["success"] is True
    assert result["test_mode"] is True
    assert result["test_recipients"] == [
        "augusto@satec.digital",
        "augusto+teste@satec.digital",
    ]
    assert result["emails_sent"] == 2
    assert mock_dispatch.await_count == 2


@pytest.mark.asyncio
async def test_campaign_sendgrid_standby_lock_forces_dry_run(db_session, monkeypatch):
    """When standby lock is enabled, sendgrid campaign must not dispatch real email."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente Standby",
        cpf_cnpj="55566677788",
        email="standby@example.com",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="REC-STANDBY",
        due_date=today - timedelta(days=1),
        amount=90.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "EMAIL_BILLING_PROVIDER", "sendgrid", raising=False)
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "sg-test-key", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_FROM", "financeiro@aisatec.com.br", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_TEST_RECIPIENTS", "", raising=False)
    monkeypatch.setattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False, raising=False)

    with patch(
        "app.services.email_billing_service._dispatch_sendgrid_email",
        new=AsyncMock(return_value=None),
    ) as mock_dispatch:
        result = await run_billing_email_campaign(db=db_session, today=today, dry_run=False)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["emails_sent"] == 0
    assert result["emails_dry_run"] == 1
    assert mock_dispatch.await_count == 0
