"""
Focused API contract tests for `status_filter` query parameter.

This suite is intentionally isolated from broader endpoint tests so CI can
validate the public filter contract even when unrelated endpoint modules change.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def created_client_id(client, sample_client_data) -> int:
    payload = dict(sample_client_data)
    payload["cpf_cnpj"] = "111.222.333-44"
    response = client.post("/api/clients/", json=payload)
    assert response.status_code == 201
    return int(response.json()["id"])


@pytest.fixture
def created_contract_id(client, created_client_id, sample_contract_data) -> int:
    payload = dict(sample_contract_data)
    payload["contract_number"] = "CTR-STATUS-FILTER-BASE"
    payload["client_id"] = created_client_id
    response = client.post("/api/contracts/", json=payload)
    assert response.status_code == 201
    return int(response.json()["id"])


class TestStatusFilterApiContract:
    def test_openapi_exposes_status_filter_for_contracts_and_signatures(self, client):
        schema = client.get("/openapi.json").json()

        contracts_params = schema["paths"]["/api/contracts/"]["get"].get("parameters", [])
        signatures_params = schema["paths"]["/api/signatures/"]["get"].get("parameters", [])

        assert any(param.get("name") == "status_filter" for param in contracts_params)
        assert any(param.get("name") == "status_filter" for param in signatures_params)
        assert not any(param.get("name") == "status" for param in contracts_params)
        assert not any(param.get("name") == "status" for param in signatures_params)

    def test_contracts_filter_by_status_filter(self, client, created_client_id, sample_contract_data):
        draft_contract = dict(sample_contract_data)
        draft_contract["client_id"] = created_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-STATUS-FILTER-DRAFT"
        assert client.post("/api/contracts/", json=draft_contract).status_code == 201

        active_contract = dict(sample_contract_data)
        active_contract["client_id"] = created_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-STATUS-FILTER-ACTIVE"
        assert client.post("/api/contracts/", json=active_contract).status_code == 201

        response = client.get("/api/contracts/?status_filter=draft")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["contract_number"] == "CTR-STATUS-FILTER-DRAFT"
        assert all(item["status"] == "draft" for item in data)

    def test_contracts_legacy_status_is_ignored(self, client, created_client_id, sample_contract_data):
        draft_contract = dict(sample_contract_data)
        draft_contract["client_id"] = created_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-LEGACY-STATUS-DRAFT"
        assert client.post("/api/contracts/", json=draft_contract).status_code == 201

        active_contract = dict(sample_contract_data)
        active_contract["client_id"] = created_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-LEGACY-STATUS-ACTIVE"
        assert client.post("/api/contracts/", json=active_contract).status_code == 201

        legacy_status_key = "".join(("sta", "tus"))
        response = client.get("/api/contracts/", params={legacy_status_key: "draft"})
        assert response.status_code == 200

        numbers = {item["contract_number"] for item in response.json()}
        assert "CTR-LEGACY-STATUS-DRAFT" in numbers
        assert "CTR-LEGACY-STATUS-ACTIVE" in numbers

    def test_signatures_filter_by_status_filter(self, client, created_contract_id):
        pending = {
            "contract_id": created_contract_id,
            "signer_name": "Joao Pending",
            "signer_email": "pending-status-filter@example.com",
            "status": "pending",
        }
        signed = {
            "contract_id": created_contract_id,
            "signer_name": "Maria Signed",
            "signer_email": "signed-status-filter@example.com",
            "status": "signed",
        }
        assert client.post("/api/signatures/", json=pending).status_code == 201
        assert client.post("/api/signatures/", json=signed).status_code == 201

        response = client.get("/api/signatures/?status_filter=pending")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["signer_email"] == "pending-status-filter@example.com"
        assert all(item["status"] == "pending" for item in data)

    def test_signatures_legacy_status_is_ignored(self, client, created_contract_id):
        pending = {
            "contract_id": created_contract_id,
            "signer_name": "Joao Pending",
            "signer_email": "pending-legacy-status@example.com",
            "status": "pending",
        }
        signed = {
            "contract_id": created_contract_id,
            "signer_name": "Maria Signed",
            "signer_email": "signed-legacy-status@example.com",
            "status": "signed",
        }
        assert client.post("/api/signatures/", json=pending).status_code == 201
        assert client.post("/api/signatures/", json=signed).status_code == 201

        legacy_status_key = "".join(("sta", "tus"))
        response = client.get("/api/signatures/", params={legacy_status_key: "pending"})
        assert response.status_code == 200

        emails = {item["signer_email"] for item in response.json()}
        assert "pending-legacy-status@example.com" in emails
        assert "signed-legacy-status@example.com" in emails
