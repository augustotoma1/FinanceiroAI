"""
Unit tests for WhatsApp billing campaign service.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.client import Client
from app.models.financial_record import FinancialRecord
from app.services.whatsapp_billing_service import (
    _classify_escalation_level,
    _normalize_phone_br,
    clear_blocked_whatsapp_targets,
    list_blocked_whatsapp_targets,
    run_whatsapp_billing_campaign,
)


def _create_client(db_session, *, name: str, cpf_cnpj: str, phone: str | None) -> Client:
    client = Client(
        name=name,
        cpf_cnpj=cpf_cnpj,
        phone=phone,
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
        transaction_date=due_date - timedelta(days=20),
        due_date=due_date,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_normalize_phone_br():
    """Phone normalization should output digits with BR country prefix."""
    assert _normalize_phone_br("(65) 99999-0001") == "5565999990001"
    assert _normalize_phone_br("5565999990001") == "5565999990001"
    assert _normalize_phone_br("") == ""


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


@pytest.mark.asyncio
async def test_campaign_dry_run_groups_by_phone_and_highest_level(db_session, monkeypatch):
    """Dry-run campaign should aggregate by phone and keep highest urgency."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente WhatsApp",
        cpf_cnpj="11111111111",
        phone="(65) 99999-0001",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="WA-001",
        due_date=today + timedelta(days=1),
        amount=200.0,
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="WA-002",
        due_date=today - timedelta(days=9),
        amount=400.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "WHATSAPP_BILLING_PROVIDER", "log", raising=False)
    result = await run_whatsapp_billing_campaign(db=db_session, today=today, dry_run=True)

    assert result["success"] is True
    assert result["eligible_clients"] == 1
    assert result["eligible_records"] == 2
    assert result["messages_dry_run"] == 1
    assert result["messages_sent"] == 0
    assert result["level_counts"]["3"] == 1


@pytest.mark.asyncio
async def test_campaign_skips_records_without_phone(db_session, monkeypatch):
    """Records without client phone must be counted as skipped."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente Sem Telefone",
        cpf_cnpj="22222222222",
        phone=None,
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="WA-003",
        due_date=today - timedelta(days=2),
        amount=350.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "WHATSAPP_BILLING_PROVIDER", "log", raising=False)
    result = await run_whatsapp_billing_campaign(db=db_session, today=today, dry_run=True)

    assert result["success"] is True
    assert result["eligible_clients"] == 0
    assert result["messages_dry_run"] == 0
    assert result["skipped_missing_phone"] == 1


@pytest.mark.asyncio
async def test_campaign_waha_dispatch_success(db_session, monkeypatch):
    """When provider is waha and dry_run false, dispatch should be awaited."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente WAHA",
        cpf_cnpj="33333333333",
        phone="(65) 98888-0001",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="WA-004",
        due_date=today - timedelta(days=1),
        amount=120.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "WHATSAPP_BILLING_PROVIDER", "waha", raising=False)
    monkeypatch.setattr(settings, "WHATSAPP_WAHA_URL", "https://waha.example.com", raising=False)

    with patch(
        "app.services.whatsapp_billing_service._dispatch_waha_text",
        new=AsyncMock(return_value=None),
    ) as mock_dispatch:
        result = await run_whatsapp_billing_campaign(db=db_session, today=today, dry_run=False)

    assert result["success"] is True
    assert result["messages_sent"] == 1
    assert result["messages_failed"] == 0
    assert mock_dispatch.await_count == 1


@pytest.mark.asyncio
async def test_campaign_blocks_no_lid_phone_and_skips_next_run(db_session, monkeypatch):
    """No LID failures should be blocked and skipped in subsequent runs."""
    today = date(2026, 2, 15)
    client = _create_client(
        db_session,
        name="Cliente No LID",
        cpf_cnpj="44444444444",
        phone="(65) 97777-0001",
    )
    _create_receivable(
        db_session,
        client_id=client.id,
        transaction_number="WA-005",
        due_date=today - timedelta(days=2),
        amount=410.0,
        status="overdue",
    )

    monkeypatch.setattr(settings, "WHATSAPP_BILLING_PROVIDER", "waha", raising=False)
    monkeypatch.setattr(settings, "WHATSAPP_WAHA_URL", "https://waha.example.com", raising=False)
    monkeypatch.setattr(settings, "WHATSAPP_BILLING_SKIP_NO_LID", True, raising=False)
    monkeypatch.setattr(settings, "WHATSAPP_BILLING_NO_LID_COOLDOWN_DAYS", 30, raising=False)

    with patch(
        "app.services.whatsapp_billing_service._dispatch_waha_text",
        new=AsyncMock(side_effect=Exception("WAHA send failed (500): No LID for user")),
    ) as mock_dispatch_first:
        first_result = await run_whatsapp_billing_campaign(db=db_session, today=today, dry_run=False)

    assert mock_dispatch_first.await_count == 1
    assert first_result["messages_failed"] == 1
    assert first_result["error_type_counts"]["no_lid"] == 1

    with patch(
        "app.services.whatsapp_billing_service._dispatch_waha_text",
        new=AsyncMock(return_value=None),
    ) as mock_dispatch_second:
        second_result = await run_whatsapp_billing_campaign(db=db_session, today=today, dry_run=False)

    assert mock_dispatch_second.await_count == 0
    assert second_result["skipped_blocked_phone"] == 1
    assert second_result["messages_sent"] == 0


def test_list_and_clear_blocked_whatsapp_targets(db_session):
    """Blocked WhatsApp targets should be listable and clearable."""
    # Seed one blocked target
    from app.models.conversation import Conversation

    db_session.add(
        Conversation(
            id="wae-5565999990001",
            messages=[],
            complete=False,
            data={
                "type": "whatsapp_error_state",
                "phone": "5565999990001",
                "reason": "no_lid",
                "fail_count": 2,
                "blocked_until": "2099-01-01T00:00:00Z",
                "last_error": "No LID for user",
            },
        )
    )
    db_session.commit()

    blocked = list_blocked_whatsapp_targets(db=db_session, limit=20)
    assert len(blocked) == 1
    assert blocked[0]["phone"] == "5565999990001"

    deleted = clear_blocked_whatsapp_targets(db=db_session, phones=["5565999990001"])
    assert deleted == 1
    assert list_blocked_whatsapp_targets(db=db_session, limit=20) == []
