"""
Unit tests for contract lifecycle service.
"""

from datetime import date

from app.models.client import Client
from app.models.contract import Contract
from app.services.contract_lifecycle_service import (
    build_contract_lifecycle_snapshot,
    mark_expired_contracts,
    resolve_contract_end_date,
)


def _create_client(db_session, *, name: str, cpf_cnpj: str) -> Client:
    client = Client(name=name, cpf_cnpj=cpf_cnpj)
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


def _create_contract(
    db_session,
    *,
    client_id: int,
    number: str,
    status: str,
    start_date: date,
    end_date: date | None = None,
    duration_months: int | None = None,
) -> Contract:
    contract = Contract(
        client_id=client_id,
        contract_number=number,
        service_description="Servico teste",
        contract_value=1000.0,
        payment_terms="mensal",
        start_date=start_date,
        end_date=end_date,
        duration_months=duration_months,
        status=status,
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    return contract


def test_resolve_contract_end_date_from_duration(db_session):
    """End date should be inferred from start_date + duration_months."""
    client = _create_client(db_session, name="Cliente A", cpf_cnpj="11111111111")
    contract = _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-001",
        status="active",
        start_date=date(2026, 1, 15),
        duration_months=2,
    )

    assert resolve_contract_end_date(contract) == date(2026, 3, 15)


def test_mark_expired_contracts_updates_status(db_session):
    """Active/signed contracts past end date should move to expired."""
    client = _create_client(db_session, name="Cliente B", cpf_cnpj="22222222222")
    contract = _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-002",
        status="active",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    result = mark_expired_contracts(db_session, reference_date=date(2026, 2, 15))
    db_session.refresh(contract)

    assert result["updated_count"] == 1
    assert contract.status == "expired"


def test_build_contract_lifecycle_snapshot_counts(db_session):
    """Snapshot should separate overdue, expiring-soon and missing-end-date."""
    client = _create_client(db_session, name="Cliente C", cpf_cnpj="33333333333")
    _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-003",
        status="signed",
        start_date=date(2025, 1, 1),
        end_date=date(2026, 2, 1),  # overdue at reference date below
    )
    _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-004",
        status="active",
        start_date=date(2025, 1, 1),
        end_date=date(2026, 2, 20),  # expiring within 30 days
    )
    _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-005",
        status="pending_signature",
        start_date=date(2026, 1, 1),
        end_date=None,
        duration_months=None,  # missing end date
    )
    _create_contract(
        db_session,
        client_id=client.id,
        number="CTR-TEST-006",
        status="cancelled",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    snapshot = build_contract_lifecycle_snapshot(
        db_session,
        reference_date=date(2026, 2, 15),
        days_ahead=30,
    )

    assert snapshot["monitored_total"] == 3
    assert snapshot["overdue_count"] == 1
    assert snapshot["expiring_soon_count"] == 1
    assert snapshot["missing_end_date_count"] == 1
