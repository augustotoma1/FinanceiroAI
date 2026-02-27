"""
Tests for client synchronization hardening rules.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.background import sync_clients as sync_clients_module
from app.background.sync_clients import (
    _normalize_tax_id,
    _sync_single_client,
    get_sync_status,
    sync_clients_job,
)
from app.models.client import Client


class TestNormalizeTaxId:
    """Validate CPF/CNPJ normalization to DB-safe values."""

    def test_prefers_valid_cpf_digits(self):
        assert _normalize_tax_id("123.456.789-01", "ca-1") == "12345678901"

    def test_truncates_long_numeric_document_to_20(self):
        raw = "9" * 80
        normalized = _normalize_tax_id(raw, "ca-2")
        assert normalized == "9" * 20
        assert len(normalized) == 20

    def test_generates_stable_placeholder_when_document_missing(self):
        normalized = _normalize_tax_id("", "conta-azul-id-123")
        assert normalized.startswith("CA-")
        assert len(normalized) <= 20


@pytest.mark.asyncio
async def test_sync_single_client_truncates_overlong_fields(db_session):
    """Sync should never produce varchar overflow in client columns."""
    very_long_email = ("cliente." + ("x" * 320) + "@empresa.com")
    customer_data = {
        "id": "ca-" + ("x" * 160),
        "nome": "Cliente Overflow Teste",
        "documento": "DOC-" + ("9" * 120),
        "telefone": "+55" + ("1" * 80),
        "email": very_long_email,
        "endereco": {
            "logradouro": "Rua " + ("A" * 500),
            "cidade": "Cidade " + ("B" * 200),
            "estado": "SAOPAULO",
            "cep": "123456789012345",
        },
    }

    created, updated = await _sync_single_client(db_session, customer_data)
    assert created is True
    assert updated is False

    db_session.flush()
    client = db_session.query(Client).filter_by(name="Cliente Overflow Teste").first()
    assert client is not None
    assert len(client.cpf_cnpj or "") <= 20
    assert len(client.phone or "") <= 20
    assert len(client.email or "") <= 255
    assert len(client.address_street or "") <= 255
    assert len(client.address_city or "") <= 100
    assert len(client.address_state or "") <= 2
    assert len(client.address_zip or "") <= 10
    assert len(client.conta_azul_id or "") <= 100


@pytest.mark.asyncio
async def test_sync_single_client_updates_existing_record_with_safe_lengths(db_session):
    """Update path must remain safe when Conta Azul sends oversized fields."""
    initial = {
        "id": "ca-update-1",
        "nome": "Cliente Atualizacao",
        "cpf": "12345678901",
        "telefone": "11999999999",
    }
    created, updated = await _sync_single_client(db_session, initial)
    assert created is True
    assert updated is False
    db_session.flush()

    oversized_update = {
        "id": "ca-update-1",
        "nome": "Cliente Atualizacao Revisado",
        "documento": "A" * 120,
        "telefone": "+55" + ("8" * 70),
        "endereco": {"estado": "MATO_GROSSO", "cep": "780000001234"},
    }
    created, updated = await _sync_single_client(db_session, oversized_update)
    assert created is False
    assert updated is True
    db_session.flush()

    client = db_session.query(Client).filter_by(conta_azul_id="ca-update-1").first()
    assert client is not None
    assert client.name == "Cliente Atualizacao Revisado"
    assert len(client.cpf_cnpj or "") <= 20
    assert len(client.phone or "") <= 20
    assert len(client.address_state or "") <= 2
    assert len(client.address_zip or "") <= 10


@pytest.mark.asyncio
async def test_sync_clients_job_reports_partial_success(monkeypatch, test_engine):
    """Job should report partial_success when some customers fail."""
    customers = [
        {"id": "ca-1", "nome": "Cliente 1", "cpf": "12345678901"},
        {"id": "ca-2", "nome": "Cliente 2", "cpf": "10987654321"},
    ]

    async def fake_get_valid_token(db):
        return "token-ok"

    class FakeContaAzulService:
        async def get_customers(self, access_token, limit):
            assert access_token == "token-ok"
            assert limit == 1000
            return customers

    async def fake_sync_single_client(db, customer_data):
        if customer_data["id"] == "ca-2":
            raise RuntimeError("forced-customer-error")
        return (True, False)

    monkeypatch.setattr(sync_clients_module, "SessionLocal", lambda: Session(bind=test_engine))
    monkeypatch.setattr(sync_clients_module, "_get_valid_conta_azul_token", fake_get_valid_token)
    monkeypatch.setattr(sync_clients_module, "ContaAzulService", FakeContaAzulService)
    monkeypatch.setattr(sync_clients_module, "_sync_single_client", fake_sync_single_client)

    result = await sync_clients_job()

    assert result["success"] is False
    assert result["partial_success"] is True
    assert result["synced_count"] == 1
    assert result["created_count"] == 1
    assert result["updated_count"] == 0
    assert result["error_count"] == 1
    assert result["errors"]


@pytest.mark.asyncio
async def test_sync_clients_job_reports_full_success(monkeypatch, test_engine):
    """Job should report success=True only when no errors happen."""
    customers = [
        {"id": "ca-10", "nome": "Cliente 10", "cpf": "12345678901"},
        {"id": "ca-11", "nome": "Cliente 11", "cpf": "10987654321"},
    ]

    async def fake_get_valid_token(db):
        return "token-ok"

    class FakeContaAzulService:
        async def get_customers(self, access_token, limit):
            assert access_token == "token-ok"
            assert limit == 1000
            return customers

    async def fake_sync_single_client(db, customer_data):
        if customer_data["id"] == "ca-10":
            return (True, False)
        return (False, True)

    monkeypatch.setattr(sync_clients_module, "SessionLocal", lambda: Session(bind=test_engine))
    monkeypatch.setattr(sync_clients_module, "_get_valid_conta_azul_token", fake_get_valid_token)
    monkeypatch.setattr(sync_clients_module, "ContaAzulService", FakeContaAzulService)
    monkeypatch.setattr(sync_clients_module, "_sync_single_client", fake_sync_single_client)

    result = await sync_clients_job()

    assert result["success"] is True
    assert result["partial_success"] is False
    assert result["synced_count"] == 2
    assert result["created_count"] == 1
    assert result["updated_count"] == 1
    assert result["error_count"] == 0


@pytest.mark.asyncio
async def test_sync_clients_job_isolates_invalid_row_with_savepoint(monkeypatch, test_engine):
    """One invalid row must not abort the whole sync batch."""
    customers = [
        {"id": "bad", "nome": "Cliente Invalido"},
        {"id": "ok", "nome": "Cliente Válido"},
    ]

    async def fake_get_valid_token(db):
        return "token-ok"

    class FakeContaAzulService:
        async def get_customers(self, access_token, limit):
            assert access_token == "token-ok"
            assert limit == 1000
            return customers

    async def fake_sync_single_client(db, customer_data):
        if customer_data["id"] == "bad":
            db.add(
                Client(
                    name=None,  # quebra NOT NULL e falha no flush deste savepoint
                    cpf_cnpj="11111111111",
                    conta_azul_id="bad",
                )
            )
            return (True, False)

        db.add(
            Client(
                name="Cliente Valido",
                cpf_cnpj="22222222222",
                conta_azul_id="ok",
            )
        )
        return (True, False)

    monkeypatch.setattr(sync_clients_module, "SessionLocal", lambda: Session(bind=test_engine))
    monkeypatch.setattr(sync_clients_module, "_get_valid_conta_azul_token", fake_get_valid_token)
    monkeypatch.setattr(sync_clients_module, "ContaAzulService", FakeContaAzulService)
    monkeypatch.setattr(sync_clients_module, "_sync_single_client", fake_sync_single_client)

    result = await sync_clients_job()

    assert result["success"] is False
    assert result["partial_success"] is True
    assert result["synced_count"] == 1
    assert result["created_count"] == 1
    assert result["updated_count"] == 0
    assert result["error_count"] == 1


@pytest.mark.asyncio
async def test_get_sync_status_missing_history(monkeypatch, test_engine):
    """Status should report missing freshness when no sync history exists."""
    monkeypatch.setattr(sync_clients_module, "SessionLocal", lambda: Session(bind=test_engine))

    status = await get_sync_status()

    assert status["sync_freshness"] == "missing"
    assert status["hours_since_last_sync"] is None


@pytest.mark.asyncio
async def test_get_sync_status_freshness_transitions(monkeypatch, test_engine):
    """Status should classify fresh/warning/stale based on last_synced_at age."""
    monkeypatch.setattr(sync_clients_module, "SessionLocal", lambda: Session(bind=test_engine))

    db = Session(bind=test_engine)
    try:
        db.query(Client).delete()
        db.commit()

        now = datetime.now(timezone.utc)
        db.add(
            Client(
                name="Cliente Fresh",
                cpf_cnpj="33333333333",
                conta_azul_id="fresh",
                last_synced_at=now - timedelta(minutes=30),
            )
        )
        db.commit()
    finally:
        db.close()

    fresh_status = await get_sync_status()
    assert fresh_status["sync_freshness"] == "fresh"
    assert float(fresh_status["hours_since_last_sync"]) < 2.0

    db = Session(bind=test_engine)
    try:
        client = db.query(Client).filter_by(conta_azul_id="fresh").first()
        client.last_synced_at = now - timedelta(hours=3)
        db.commit()
    finally:
        db.close()

    warning_status = await get_sync_status()
    assert warning_status["sync_freshness"] == "warning"

    db = Session(bind=test_engine)
    try:
        client = db.query(Client).filter_by(conta_azul_id="fresh").first()
        client.last_synced_at = now - timedelta(hours=8)
        db.commit()
    finally:
        db.close()

    stale_status = await get_sync_status()
    assert stale_status["sync_freshness"] == "stale"
