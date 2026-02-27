from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.services import signature_sync_service


@pytest.mark.asyncio
async def test_sync_signatures_marks_contract_signed_when_all_signed(db_session, monkeypatch):
    client = Client(name="Cliente Sync", cpf_cnpj="12345678900")
    db_session.add(client)
    db_session.flush()

    contract = Contract(
        client_id=client.id,
        contract_number="SYNC-CTR-001",
        service_description="Serviço de teste",
        contract_value=Decimal("1000.00"),
        payment_terms="Mensal",
        start_date=date.today() + timedelta(days=5),
        status="pending_signature",
        autentique_document_id="doc-sync-1",
    )
    db_session.add(contract)
    db_session.flush()

    local_signature = Signature(
        contract_id=contract.id,
        signer_name="Assinante",
        signer_email="assinante@example.com",
        status="pending",
        autentique_signature_id="sig-1",
    )
    db_session.add(local_signature)
    db_session.commit()

    class _FakeService:
        async def get_document_status(self, document_id: str):
            assert document_id == "doc-sync-1"
            return {
                "id": document_id,
                "signatures": [
                    {
                        "public_id": "sig-1",
                        "name": "Assinante",
                        "email": "assinante@example.com",
                        "signed": {"created_at": "2026-02-15T20:00:00Z"},
                        "rejected": None,
                        "link": {"short_link": "https://autentique.test/sig-1"},
                    }
                ],
            }

    monkeypatch.setattr(signature_sync_service, "AutentiqueService", lambda: _FakeService())

    result = await signature_sync_service.sync_signatures_from_autentique(
        db_session,
        max_contracts=10,
    )

    assert result["success"] is True
    assert result["processed_contracts"] == 1

    db_session.refresh(contract)
    db_session.refresh(local_signature)
    assert contract.status == "signed"
    assert contract.signed_at is not None
    assert local_signature.status == "signed"
    assert local_signature.signed_at is not None


@pytest.mark.asyncio
async def test_sync_signatures_keeps_contract_pending_when_any_pending(db_session, monkeypatch):
    client = Client(name="Cliente Sync 2", cpf_cnpj="12345678901")
    db_session.add(client)
    db_session.flush()

    contract = Contract(
        client_id=client.id,
        contract_number="SYNC-CTR-002",
        service_description="Serviço de teste",
        contract_value=Decimal("2000.00"),
        payment_terms="Mensal",
        start_date=date.today(),
        status="draft",
        autentique_document_id="doc-sync-2",
    )
    db_session.add(contract)
    db_session.commit()

    class _FakeService:
        async def get_document_status(self, document_id: str):
            assert document_id == "doc-sync-2"
            return {
                "id": document_id,
                "signatures": [
                    {
                        "public_id": "sig-2a",
                        "name": "Signer A",
                        "email": "a@example.com",
                        "signed": {"created_at": "2026-02-15T20:00:00Z"},
                        "rejected": None,
                        "link": {"short_link": "https://autentique.test/sig-2a"},
                    },
                    {
                        "public_id": "sig-2b",
                        "name": "Signer B",
                        "email": "b@example.com",
                        "signed": None,
                        "rejected": None,
                        "link": {"short_link": "https://autentique.test/sig-2b"},
                    },
                ],
            }

    monkeypatch.setattr(signature_sync_service, "AutentiqueService", lambda: _FakeService())

    result = await signature_sync_service.sync_signatures_from_autentique(
        db_session,
        max_contracts=10,
    )

    assert result["success"] is True
    assert result["processed_contracts"] == 1
    assert result["created_signatures"] == 2

    db_session.refresh(contract)
    assert contract.status == "pending_signature"
