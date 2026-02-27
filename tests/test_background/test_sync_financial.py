"""
Tests for financial synchronization status contract.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

import app.background.sync_financial as sync_financial
from app.models.client import Client
from app.models.financial_record import FinancialRecord
from app.services.conta_azul_service import ContaAzulError
from sqlalchemy.orm import Session as SASession


class _DummyNestedTx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummySession:
    def begin_nested(self):
        return _DummyNestedTx()

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def test_resolve_sync_window_accepts_valid_iso_range():
    start, end = sync_financial._resolve_sync_window("2026-02-01", "2026-02-28")
    assert start == "2026-02-01"
    assert end == "2026-02-28"


def test_resolve_sync_window_rejects_inverted_range():
    with pytest.raises(sync_financial.FinancialSyncDataError):
        sync_financial._resolve_sync_window("2026-03-01", "2026-02-28")


@pytest.mark.asyncio
async def test_sync_financial_marks_partial_success_when_one_source_fails(monkeypatch):
    monkeypatch.setattr(sync_financial, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(sync_financial, "_build_sync_window", lambda: ("2026-01-01", "2026-12-31"))

    async def _fake_get_token(db):  # pragma: no cover - signature compatibility
        return "token-ok"

    class _FakeService:
        pass

    async def _fake_fetch(*, service, access_token, endpoint, **kwargs):
        if "contas-a-receber" in endpoint:
            return [{"id": "rec-1"}]
        raise ContaAzulError("simulated source failure")

    def _fake_sync_single(db, transaction_data):
        return (True, False)

    monkeypatch.setattr(sync_financial, "_get_valid_conta_azul_token", _fake_get_token)
    monkeypatch.setattr(sync_financial, "ContaAzulService", _FakeService)
    monkeypatch.setattr(sync_financial, "_fetch_financial_items_paginated", _fake_fetch)
    monkeypatch.setattr(sync_financial, "_sync_single_transaction", _fake_sync_single)

    result = await sync_financial.sync_financial_job()

    assert result["success"] is False
    assert result["partial_success"] is True
    assert result["synced_count"] == 1
    assert result["source_totals"]["receber"] == 1
    assert result["source_totals"]["pagar"] == 0
    assert result["error_count"] == 1


@pytest.mark.asyncio
async def test_sync_financial_success_true_without_errors(monkeypatch):
    monkeypatch.setattr(sync_financial, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(sync_financial, "_build_sync_window", lambda: ("2026-01-01", "2026-12-31"))

    async def _fake_get_token(db):  # pragma: no cover - signature compatibility
        return "token-ok"

    class _FakeService:
        pass

    async def _fake_fetch(*, service, access_token, endpoint, **kwargs):
        if "contas-a-receber" in endpoint:
            return [{"id": "rec-1"}]
        return [{"id": "pag-1"}]

    def _fake_sync_single(db, transaction_data):
        return (True, False)

    monkeypatch.setattr(sync_financial, "_get_valid_conta_azul_token", _fake_get_token)
    monkeypatch.setattr(sync_financial, "ContaAzulService", _FakeService)
    monkeypatch.setattr(sync_financial, "_fetch_financial_items_paginated", _fake_fetch)
    monkeypatch.setattr(sync_financial, "_sync_single_transaction", _fake_sync_single)

    result = await sync_financial.sync_financial_job()

    assert result["success"] is True
    assert result["partial_success"] is False
    assert result["synced_count"] == 2
    assert result["error_count"] == 0
    assert result["source_totals"]["receber"] == 1
    assert result["source_totals"]["pagar"] == 1


@pytest.mark.asyncio
async def test_sync_financial_all_sources_failed_returns_full_failure(monkeypatch):
    monkeypatch.setattr(sync_financial, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(sync_financial, "_build_sync_window", lambda: ("2026-01-01", "2026-12-31"))

    async def _fake_get_token(db):  # pragma: no cover - signature compatibility
        return "token-ok"

    class _FakeService:
        pass

    async def _fake_fetch(*, service, access_token, endpoint, **kwargs):
        raise ContaAzulError("source offline")

    monkeypatch.setattr(sync_financial, "_get_valid_conta_azul_token", _fake_get_token)
    monkeypatch.setattr(sync_financial, "ContaAzulService", _FakeService)
    monkeypatch.setattr(sync_financial, "_fetch_financial_items_paginated", _fake_fetch)

    result = await sync_financial.sync_financial_job()

    assert result["success"] is False
    assert result["partial_success"] is False
    assert result["synced_count"] == 0
    assert result["error_count"] == 2
    assert result["source_totals"]["receber"] == 0
    assert result["source_totals"]["pagar"] == 0


@pytest.mark.asyncio
async def test_sync_financial_forwards_custom_window_to_fetch(monkeypatch):
    monkeypatch.setattr(sync_financial, "SessionLocal", lambda: _DummySession())

    async def _fake_get_token(db):  # pragma: no cover - signature compatibility
        return "token-ok"

    class _FakeService:
        pass

    seen_params = []

    async def _fake_fetch(*, service, access_token, endpoint, data_vencimento_de, data_vencimento_ate, **kwargs):
        seen_params.append((endpoint, data_vencimento_de, data_vencimento_ate))
        return []

    monkeypatch.setattr(sync_financial, "_get_valid_conta_azul_token", _fake_get_token)
    monkeypatch.setattr(sync_financial, "ContaAzulService", _FakeService)
    monkeypatch.setattr(sync_financial, "_fetch_financial_items_paginated", _fake_fetch)

    result = await sync_financial.sync_financial_job(
        data_vencimento_de="2026-02-01",
        data_vencimento_ate="2026-02-28",
    )

    assert result["window"]["data_vencimento_de"] == "2026-02-01"
    assert result["window"]["data_vencimento_ate"] == "2026-02-28"
    assert len(seen_params) == 2
    assert all(item[1] == "2026-02-01" and item[2] == "2026-02-28" for item in seen_params)


@pytest.mark.asyncio
async def test_get_financial_sync_status_returns_aggregates(db_session, monkeypatch):
    monkeypatch.setattr(sync_financial, "SessionLocal", lambda: SASession(bind=db_session.bind))

    client = Client(
        name="Cliente Financeiro",
        cpf_cnpj="12345678901",
        conta_azul_id="cli-1",
    )
    db_session.add(client)
    db_session.flush()

    now = datetime.now(timezone.utc)
    records = [
        FinancialRecord(
            client_id=client.id,
            transaction_type="receivable",
            transaction_number="REC-1",
            description="Receber 1",
            amount=Decimal("100.00"),
            currency="BRL",
            status="overdue",
            transaction_date=date(2026, 2, 1),
            due_date=date(2026, 2, 10),
            conta_azul_id="receber:1",
            last_synced_at=now,
        ),
        FinancialRecord(
            client_id=client.id,
            transaction_type="payable",
            transaction_number="PAG-1",
            description="Pagar 1",
            amount=Decimal("80.00"),
            currency="BRL",
            status="paid",
            transaction_date=date(2026, 2, 2),
            due_date=date(2026, 2, 9),
            conta_azul_id="pagar:1",
            last_synced_at=now,
        ),
        FinancialRecord(
            client_id=client.id,
            transaction_type="receivable",
            transaction_number="REC-LOCAL-1",
            description="Receber local",
            amount=Decimal("50.00"),
            currency="BRL",
            status="pending",
            transaction_date=date(2026, 2, 3),
            due_date=date(2026, 2, 20),
            conta_azul_id=None,
            last_synced_at=None,
        ),
    ]
    db_session.add_all(records)
    db_session.commit()

    status = await sync_financial.get_financial_sync_status()

    assert status["total_records"] == 3
    assert status["synced_records"] == 2
    assert status["receivable_records"] == 2
    assert status["payable_records"] == 1
    assert status["overdue_records"] == 1
    assert status["last_sync_time"] is not None
