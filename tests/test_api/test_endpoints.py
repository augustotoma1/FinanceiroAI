"""
Integration Tests for API Endpoints

Tests cover all API endpoints including:
- Conversation endpoints (conversational AI with Claude)
- Client management endpoints (CRUD operations)
- Contract management endpoints (CRUD operations with client validation)
- Signature endpoints (electronic signature workflow)
- Auth endpoints (OAuth flow for Conta Azul)
- Dashboard endpoints (KPI metrics)

All tests use the FastAPI TestClient with test database isolation.
"""

import pytest
from unittest.mock import patch, Mock, MagicMock, AsyncMock
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import re
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.models.integration_token import IntegrationToken
from app.models.conversation import Conversation
from app.models.oauth_state import OAuthState
from app.services.autentique_service import AutentiqueAPIError


@pytest.fixture
def unauthenticated_client(db_session):
    """Test client without default API key header."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ============================================================================
# API Security Tests
# ============================================================================

class TestApiSecurity:
    """Ensure critical routers are always protected by API key auth."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/clients/"),
            ("get", "/api/contracts/"),
            ("get", "/api/signatures/"),
            ("get", "/api/dashboard/metrics"),
            ("post", "/api/conversation/start"),
        ],
    )
    def test_critical_routes_require_api_key(self, unauthenticated_client, method, path):
        """Requests without auth headers must be rejected."""
        response = getattr(unauthenticated_client, method)(path)
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/clients/"),
            ("get", "/api/contracts/"),
            ("get", "/api/signatures/"),
            ("get", "/api/dashboard/metrics"),
            ("post", "/api/conversation/start"),
        ],
    )
    def test_critical_routes_reject_invalid_api_key(self, unauthenticated_client, method, path):
        """Invalid API keys must be rejected consistently."""
        response = getattr(unauthenticated_client, method)(
            path,
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"


# ============================================================================
# Test Suite Guardrails
# ============================================================================

class TestSuiteGuardrails:
    """Prevent accidental regressions in test contracts."""

    def test_endpoints_suite_does_not_use_legacy_status_query_literal(self):
        """
        Legacy query parameter literal (`status`) must not be used directly in
        endpoint URL strings; current contract uses `status_filter`.
        """
        content = Path(__file__).read_text(encoding="utf-8")
        query_key = "".join(("sta", "tus"))
        assert f"?{query_key}=" not in content
        assert f"&{query_key}=" not in content

    def test_endpoints_suite_does_not_use_legacy_status_params_mapping(self):
        """
        Filtering tests must not pass legacy `status` via `params={...}`.
        This guard catches accidental reintroduction of old query-contract usage.
        """
        content = Path(__file__).read_text(encoding="utf-8")
        legacy_params_pattern = re.compile(
            r'client\.get\(\s*"/api/(contracts|signatures)/"\s*,\s*params\s*=\s*\{[^}]*["\']status["\']\s*:',
            flags=re.DOTALL,
        )
        assert legacy_params_pattern.search(content) is None

    def test_openapi_uses_status_filter_query_param_for_contracts_and_signatures(self, client):
        """
        API schema must expose `status_filter` (and not `status`) for filtering.
        This keeps the public contract aligned with endpoint tests.
        """
        schema = client.get("/openapi.json").json()

        contracts_params = schema["paths"]["/api/contracts/"]["get"].get("parameters", [])
        signatures_params = schema["paths"]["/api/signatures/"]["get"].get("parameters", [])

        assert any(param.get("name") == "status_filter" for param in contracts_params)
        assert any(param.get("name") == "status_filter" for param in signatures_params)
        assert not any(param.get("name") == "status" for param in contracts_params)
        assert not any(param.get("name") == "status" for param in signatures_params)


# ============================================================================
# Conversation Endpoints Tests
# ============================================================================

class TestConversationEndpoints:
    """Test conversational AI endpoints"""

    def test_start_conversation_success(self, client):
        """Test starting a new conversation returns conversation ID and greeting"""
        # Mock Claude service — send_message is async, needs AsyncMock
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello! I'll help you create a service contract."
            mock_claude.return_value = mock_service

            response = client.post("/api/conversation/start")

            assert response.status_code == 201
            data = response.json()
            assert "conversation_id" in data
            assert "message" in data
            assert "created_at" in data
            assert data["message"] == "Hello! I'll help you create a service contract."

    def test_send_message_success(self, client):
        """Test sending a message in an existing conversation"""
        # First, start a conversation — both methods are async
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello! I'll help you create a service contract."
            mock_claude.return_value = mock_service

            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            # Mock continuing conversation — collect_contract_data is async too
            mock_service.collect_contract_data.return_value = {
                "complete": False,
                "message": "Great! What's the client's CPF or CNPJ?"
            }

            # Send a message
            message_response = client.post(
                f"/api/conversation/{conversation_id}/message",
                json={"message": "The client name is João Silva"}
            )

            assert message_response.status_code == 200
            data = message_response.json()
            assert data["conversation_id"] == conversation_id
            assert data["user_message"] == "The client name is João Silva"
            assert "assistant_message" in data
            assert data["complete"] is False
            assert "timestamp" in data

    def test_send_message_conversation_not_found(self, client):
        """Test sending message to non-existent conversation returns 404"""
        response = client.post(
            "/api/conversation/invalid-id/message",
            json={"message": "Hello"}
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_send_message_empty_message(self, client):
        """Test sending empty message returns validation error"""
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello!"
            mock_claude.return_value = mock_service
            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            response = client.post(
                f"/api/conversation/{conversation_id}/message",
                json={"message": ""}
            )

            assert response.status_code == 422  # Validation error

    def test_get_conversation_success(self, client):
        """Test retrieving conversation details"""
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello! I'll help you create a service contract."
            mock_claude.return_value = mock_service

            # Start conversation
            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            # Get conversation details
            get_response = client.get(f"/api/conversation/{conversation_id}")

            assert get_response.status_code == 200
            data = get_response.json()
            assert data["conversation_id"] == conversation_id
            assert "messages" in data
            assert "complete" in data
            assert "created_at" in data

    def test_get_conversation_not_found(self, client):
        """Test getting non-existent conversation returns 404"""
        response = client.get("/api/conversation/invalid-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_conversation_expired_returns_404(self, client, db_session):
        """Test expired conversations are not retrievable."""
        with patch("app.api.conversation.ClaudeService") as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello!"
            mock_claude.return_value = mock_service

            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            conversation = db_session.get(Conversation, conversation_id)
            conversation.updated_at = datetime.now(timezone.utc) - timedelta(hours=72)
            db_session.commit()

            get_response = client.get(f"/api/conversation/{conversation_id}")
            assert get_response.status_code == 404
            assert "not found" in get_response.json()["detail"].lower()
            assert db_session.get(Conversation, conversation_id) is None

    def test_delete_conversation_success(self, client):
        """Test deleting a conversation"""
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello!"
            mock_claude.return_value = mock_service

            # Start conversation
            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            # Delete conversation
            delete_response = client.delete(f"/api/conversation/{conversation_id}")

            assert delete_response.status_code == 204

            # Verify conversation is deleted
            get_response = client.get(f"/api/conversation/{conversation_id}")
            assert get_response.status_code == 404

    def test_conversation_completion_with_data(self, client):
        """Test conversation completion returns collected data"""
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello!"
            mock_claude.return_value = mock_service

            # Start conversation
            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            # Mock completion with data
            complete_data = {
                "client_name": "João Silva",
                "cpf_cnpj": "123.456.789-00",
                "service_description": "Consultoria",
                "contract_value": 5000.00
            }
            mock_service.collect_contract_data.return_value = {
                "complete": True,
                "data": complete_data
            }

            # Send final message
            message_response = client.post(
                f"/api/conversation/{conversation_id}/message",
                json={"message": "Yes, that's correct"}
            )

            assert message_response.status_code == 200
            data = message_response.json()
            assert data["complete"] is True
            assert data["data"] == complete_data

    def test_send_message_expired_conversation_returns_404(self, client, db_session):
        """Test expired conversations cannot receive new messages."""
        with patch("app.api.conversation.ClaudeService") as mock_claude:
            mock_service = AsyncMock()
            mock_service.send_message.return_value = "Hello!"
            mock_claude.return_value = mock_service

            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            conversation = db_session.get(Conversation, conversation_id)
            conversation.updated_at = datetime.now(timezone.utc) - timedelta(hours=72)
            db_session.commit()

            message_response = client.post(
                f"/api/conversation/{conversation_id}/message",
                json={"message": "still there?"},
            )
            assert message_response.status_code == 404
            assert "not found" in message_response.json()["detail"].lower()
            assert db_session.get(Conversation, conversation_id) is None


# ============================================================================
# Client Endpoints Tests
# ============================================================================

class TestClientEndpoints:
    """Test client management endpoints"""

    def test_create_client_success(self, client, sample_client_data):
        """Test creating a new client returns 201 with client data"""
        response = client.post("/api/clients/", json=sample_client_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_client_data["name"]
        assert data["email"] == sample_client_data["email"]
        assert data["cpf_cnpj"] == sample_client_data["cpf_cnpj"]
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_client_duplicate_cpf_cnpj(self, client, sample_client_data):
        """Test creating client with duplicate CPF/CNPJ returns 409"""
        # Create first client
        client.post("/api/clients/", json=sample_client_data)

        # Attempt to create duplicate
        response = client.post("/api/clients/", json=sample_client_data)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_client_invalid_email(self, client, sample_client_data):
        """Test creating client with invalid email returns 422"""
        sample_client_data["email"] = "invalid-email"
        response = client.post("/api/clients/", json=sample_client_data)

        assert response.status_code == 422

    def test_create_client_missing_required_fields(self, client):
        """Test creating client without required fields returns 422"""
        incomplete_data = {
            "name": "Test Client"
            # Missing required fields
        }
        response = client.post("/api/clients/", json=incomplete_data)

        assert response.status_code == 422

    def test_list_clients_empty(self, client):
        """Test listing clients when database is empty"""
        response = client.get("/api/clients/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_clients_with_data(self, client, sample_client_data):
        """Test listing clients returns all clients"""
        # Create two clients
        client.post("/api/clients/", json=sample_client_data)

        client_data_2 = sample_client_data.copy()
        client_data_2["cpf_cnpj"] = "111.222.333-44"
        client_data_2["email"] = "client2@example.com"
        client.post("/api/clients/", json=client_data_2)

        # List clients
        response = client.get("/api/clients/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_clients_with_pagination(self, client, sample_client_data):
        """Test listing clients with pagination parameters"""
        # Create three clients
        for i in range(3):
            client_data = sample_client_data.copy()
            client_data["cpf_cnpj"] = f"{i}{i}{i}.{i}{i}{i}.{i}{i}{i}-{i}{i}"
            client_data["email"] = f"client{i}@example.com"
            client.post("/api/clients/", json=client_data)

        # Get first page (limit=2)
        response = client.get("/api/clients/?skip=0&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_clients_with_search(self, client, sample_client_data):
        """Test listing clients with search filter"""
        # Create client
        client.post("/api/clients/", json=sample_client_data)

        # Search by name
        response = client.get(f"/api/clients/?search={sample_client_data['name']}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["name"] == sample_client_data["name"] for c in data)

    def test_get_client_by_id_success(self, client, sample_client_data):
        """Test getting client by ID returns client data"""
        # Create client
        create_response = client.post("/api/clients/", json=sample_client_data)
        client_id = create_response.json()["id"]

        # Get client
        response = client.get(f"/api/clients/{client_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == client_id
        assert data["name"] == sample_client_data["name"]

    def test_get_client_by_id_not_found(self, client):
        """Test getting non-existent client returns 404"""
        response = client.get("/api/clients/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_client_success(self, client, sample_client_data):
        """Test updating client returns updated data"""
        # Create client
        create_response = client.post("/api/clients/", json=sample_client_data)
        client_id = create_response.json()["id"]

        # Update client
        update_data = {"name": "Updated Name", "email": "updated@example.com"}
        response = client.put(f"/api/clients/{client_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["email"] == "updated@example.com"

    def test_update_client_partial(self, client, sample_client_data):
        """Test partial update of client (only some fields)"""
        # Create client
        create_response = client.post("/api/clients/", json=sample_client_data)
        client_id = create_response.json()["id"]
        original_email = create_response.json()["email"]

        # Partial update (only name)
        update_data = {"name": "New Name Only"}
        response = client.put(f"/api/clients/{client_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name Only"
        assert data["email"] == original_email  # Email unchanged

    def test_update_client_not_found(self, client):
        """Test updating non-existent client returns 404"""
        update_data = {"name": "Test"}
        response = client.put("/api/clients/99999", json=update_data)

        assert response.status_code == 404

    def test_delete_client_success(self, client, sample_client_data):
        """Test deleting client returns 204"""
        # Create client
        create_response = client.post("/api/clients/", json=sample_client_data)
        client_id = create_response.json()["id"]

        # Delete client
        response = client.delete(f"/api/clients/{client_id}")

        assert response.status_code == 204

        # Verify client is deleted
        get_response = client.get(f"/api/clients/{client_id}")
        assert get_response.status_code == 404

    def test_delete_client_not_found(self, client):
        """Test deleting non-existent client returns 404"""
        response = client.delete("/api/clients/99999")

        assert response.status_code == 404


# ============================================================================
# Contract Endpoints Tests
# ============================================================================

class TestContractEndpoints:
    """Test contract management endpoints"""

    @pytest.fixture
    def test_client_id(self, client, sample_client_data):
        """Create a test client and return its ID"""
        response = client.post("/api/clients/", json=sample_client_data)
        return response.json()["id"]

    def test_create_contract_success(self, client, test_client_id, sample_contract_data):
        """Test creating a new contract returns 201 with contract data"""
        sample_contract_data["client_id"] = test_client_id
        response = client.post("/api/contracts/", json=sample_contract_data)

        assert response.status_code == 201
        data = response.json()
        assert data["client_id"] == test_client_id
        assert data["contract_number"] == sample_contract_data["contract_number"]
        assert data["service_description"] == sample_contract_data["service_description"]
        assert "id" in data
        assert "created_at" in data

    def test_create_contract_client_not_found(self, client, sample_contract_data):
        """Test creating contract with non-existent client returns 404"""
        sample_contract_data["client_id"] = 99999
        response = client.post("/api/contracts/", json=sample_contract_data)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_contract_duplicate_number(self, client, test_client_id, sample_contract_data):
        """Test creating contract with duplicate number returns 409"""
        sample_contract_data["client_id"] = test_client_id

        # Create first contract
        client.post("/api/contracts/", json=sample_contract_data)

        # Attempt to create duplicate
        response = client.post("/api/contracts/", json=sample_contract_data)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_list_contracts_empty(self, client):
        """Test listing contracts when database is empty"""
        response = client.get("/api/contracts/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_contracts_with_data(self, client, test_client_id, sample_contract_data):
        """Test listing contracts returns all contracts"""
        sample_contract_data["client_id"] = test_client_id

        # Create two contracts
        client.post("/api/contracts/", json=sample_contract_data)

        contract_data_2 = sample_contract_data.copy()
        contract_data_2["contract_number"] = "CTR-2026-002"
        client.post("/api/contracts/", json=contract_data_2)

        # List contracts
        response = client.get("/api/contracts/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_contracts_filter_by_client(self, client, test_client_id, sample_contract_data):
        """Test filtering contracts by client_id"""
        sample_contract_data["client_id"] = test_client_id
        client.post("/api/contracts/", json=sample_contract_data)

        # Filter by client_id
        response = client.get(f"/api/contracts/?client_id={test_client_id}")

        assert response.status_code == 200
        data = response.json()
        assert all(c["client_id"] == test_client_id for c in data)

    def test_list_contracts_filter_by_status_filter(self, client, test_client_id, sample_contract_data):
        """Test filtering contracts by status_filter query param."""
        # Create one draft contract (target status)
        draft_contract = sample_contract_data.copy()
        draft_contract["client_id"] = test_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-2026-FILTER-DRAFT"
        client.post("/api/contracts/", json=draft_contract)

        # Create one active contract (should be excluded by filter)
        active_contract = sample_contract_data.copy()
        active_contract["client_id"] = test_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-2026-FILTER-ACTIVE"
        client.post("/api/contracts/", json=active_contract)

        # Filter by status_filter (query param name in the route)
        response = client.get("/api/contracts/?status_filter=draft")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["contract_number"] == "CTR-2026-FILTER-DRAFT"
        assert all(c["status"] == "draft" for c in data)

    def test_list_contracts_filter_by_status_filter_only(self, client, test_client_id, sample_contract_data):
        """Test filtering contracts using status_filter query param only."""
        draft_contract = sample_contract_data.copy()
        draft_contract["client_id"] = test_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-2026-LEGACY-DRAFT"
        client.post("/api/contracts/", json=draft_contract)

        active_contract = sample_contract_data.copy()
        active_contract["client_id"] = test_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-2026-LEGACY-ACTIVE"
        client.post("/api/contracts/", json=active_contract)

        response = client.get("/api/contracts/?status_filter=draft")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["contract_number"] == "CTR-2026-LEGACY-DRAFT"
        assert all(c["status"] == "draft" for c in data)

    def test_list_contracts_status_filter_ignores_unrelated_query_param(
        self,
        client,
        test_client_id,
        sample_contract_data,
    ):
        """Filtering must rely on status_filter even when unrelated params are present."""
        draft_contract = sample_contract_data.copy()
        draft_contract["client_id"] = test_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-2026-LEGACY-STATUS-DRAFT"
        client.post("/api/contracts/", json=draft_contract)

        active_contract = sample_contract_data.copy()
        active_contract["client_id"] = test_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-2026-LEGACY-STATUS-ACTIVE"
        client.post("/api/contracts/", json=active_contract)

        response = client.get("/api/contracts/?status_filter=draft&legacy_filter=active")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["contract_number"] == "CTR-2026-LEGACY-STATUS-DRAFT"
        assert all(item["status"] == "draft" for item in data)

    def test_list_contracts_legacy_status_query_param_is_ignored(
        self,
        client,
        test_client_id,
        sample_contract_data,
    ):
        """Legacy status query param must be ignored by current contracts route."""
        draft_contract = sample_contract_data.copy()
        draft_contract["client_id"] = test_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-2026-LEGACY-STATUS-IGNORED-DRAFT"
        client.post("/api/contracts/", json=draft_contract)

        active_contract = sample_contract_data.copy()
        active_contract["client_id"] = test_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-2026-LEGACY-STATUS-IGNORED-ACTIVE"
        client.post("/api/contracts/", json=active_contract)

        # Legacy status param should be ignored; both records must remain visible.
        legacy_status_key = "".join(("sta", "tus"))
        response = client.get("/api/contracts/", params={legacy_status_key: "draft"})

        assert response.status_code == 200
        data = response.json()
        numbers = {item["contract_number"] for item in data}
        assert "CTR-2026-LEGACY-STATUS-IGNORED-DRAFT" in numbers
        assert "CTR-2026-LEGACY-STATUS-IGNORED-ACTIVE" in numbers

    def test_list_contracts_status_filter_takes_precedence_over_legacy_status(
        self,
        client,
        test_client_id,
        sample_contract_data,
    ):
        """When both are present, only status_filter must drive contracts filtering."""
        draft_contract = sample_contract_data.copy()
        draft_contract["client_id"] = test_client_id
        draft_contract["status"] = "draft"
        draft_contract["contract_number"] = "CTR-2026-STATUS-FILTER-PRECEDENCE-DRAFT"
        client.post("/api/contracts/", json=draft_contract)

        active_contract = sample_contract_data.copy()
        active_contract["client_id"] = test_client_id
        active_contract["status"] = "active"
        active_contract["contract_number"] = "CTR-2026-STATUS-FILTER-PRECEDENCE-ACTIVE"
        client.post("/api/contracts/", json=active_contract)

        legacy_status_key = "".join(("sta", "tus"))
        response = client.get(
            "/api/contracts/",
            params={"status_filter": "draft", legacy_status_key: "active"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["contract_number"] == "CTR-2026-STATUS-FILTER-PRECEDENCE-DRAFT"
        assert all(item["status"] == "draft" for item in data)

    def test_get_contract_by_id_success(self, client, test_client_id, sample_contract_data):
        """Test getting contract by ID returns contract data"""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        # Get contract
        response = client.get(f"/api/contracts/{contract_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == contract_id
        assert data["contract_number"] == sample_contract_data["contract_number"]

    def test_get_contract_by_id_not_found(self, client):
        """Test getting non-existent contract returns 404"""
        response = client.get("/api/contracts/99999")

        assert response.status_code == 404

    def test_update_contract_success(self, client, test_client_id, sample_contract_data):
        """Test updating contract returns updated data"""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        # Update contract
        update_data = {
            "service_description": "Updated service description",
            "status": "active"
        }
        response = client.put(f"/api/contracts/{contract_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["service_description"] == "Updated service description"
        assert data["status"] == "active"

    def test_update_contract_not_found(self, client):
        """Test updating non-existent contract returns 404"""
        update_data = {"status": "active"}
        response = client.put("/api/contracts/99999", json=update_data)

        assert response.status_code == 404

    def test_delete_contract_success(self, client, test_client_id, sample_contract_data):
        """Test deleting contract returns 204"""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        # Delete contract
        response = client.delete(f"/api/contracts/{contract_id}")

        assert response.status_code == 204

        # Verify contract is deleted
        get_response = client.get(f"/api/contracts/{contract_id}")
        assert get_response.status_code == 404

    def test_delete_contract_not_found(self, client):
        """Test deleting non-existent contract returns 404"""
        response = client.delete("/api/contracts/99999")

        assert response.status_code == 404

    def test_list_contract_templates(self, client):
        """Template catalog endpoint should expose available Jinja2 contract templates."""
        response = client.get("/api/contracts/templates/available")

        assert response.status_code == 200
        data = response.json()
        assert data["default_template"] == "default_contract.html"
        assert "default_contract.html" in data["templates"]
        assert data["total"] >= 1

    def test_preview_contract_template_success(self, client, test_client_id, sample_contract_data):
        """Contract preview should render selected template to HTML."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        with patch("app.api.contracts.ContractGenerator") as mock_generator_cls:
            generator = Mock()
            generator.generate_contract_html = AsyncMock(return_value="<html><body>preview</body></html>")
            mock_generator_cls.return_value = generator

            response = client.get(f"/api/contracts/{contract_id}/preview?template_name=default_contract.html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "preview" in response.text
        generator.generate_contract_html.assert_awaited_once()

    def test_generate_contract_pdf_success(self, client, test_client_id, sample_contract_data):
        """Contract PDF endpoint should stream generated PDF bytes."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        with patch("app.api.contracts.ContractGenerator") as mock_generator_cls:
            generator = Mock()
            generator.generate_contract_pdf = AsyncMock(return_value=b"%PDF-1.4 mock")
            mock_generator_cls.return_value = generator

            response = client.get(f"/api/contracts/{contract_id}/pdf?template_name=default_contract.html")

        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
        assert "application/pdf" in response.headers["content-type"]
        assert "content-disposition" in response.headers
        generator.generate_contract_pdf.assert_awaited_once()

    def test_send_contract_for_signature_success(
        self,
        client,
        db_session,
        test_client_id,
        sample_contract_data,
    ):
        """Dispatch endpoint should generate PDF, call Autentique and persist signatures."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        with patch("app.services.contract_signature_service.ContractGenerator") as mock_generator_cls:
            generator = Mock()
            generator.generate_contract_pdf = AsyncMock(return_value=b"%PDF-1.4 mock")
            mock_generator_cls.return_value = generator

            with patch("app.services.contract_signature_service.AutentiqueService") as mock_autentique_cls:
                autentique = Mock()
                autentique.create_document = AsyncMock(
                    return_value={
                        "id": "doc-test-123",
                        "signatures": [
                            {
                                "public_id": "sig-public-1",
                                "name": "Assinante Teste",
                                "email": "assinante.teste@example.com",
                                "action": "SIGN",
                                "link": {"short_link": "https://aut.ent/sig1"},
                                "signed": None,
                                "rejected": None,
                            }
                        ],
                    }
                )
                mock_autentique_cls.return_value = autentique

                response = client.post(
                    f"/api/contracts/{contract_id}/send-for-signature",
                    json={
                        "template_name": "default_contract.html",
                        "show_audit_page": True,
                        "signers": [
                            {
                                "name": "Assinante Teste",
                                "email": "assinante.teste@example.com",
                                "cpf": "12345678901",
                            }
                        ],
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == contract_id
        assert data["autentique_document_id"] == "doc-test-123"
        assert data["status"] == "pending_signature"
        assert data["signers_created"] == 1
        assert data["signers_updated"] == 0
        assert len(data["signatures"]) == 1
        assert data["signatures"][0]["autentique_signature_id"] == "sig-public-1"

        contract = db_session.query(Contract).filter(Contract.id == contract_id).first()
        assert contract is not None
        assert contract.autentique_document_id == "doc-test-123"
        assert contract.status == "pending_signature"

        signatures = db_session.query(Signature).filter(Signature.contract_id == contract_id).all()
        assert len(signatures) == 1
        assert signatures[0].signer_email == "assinante.teste@example.com"
        assert signatures[0].autentique_signature_id == "sig-public-1"

    def test_send_contract_for_signature_defaults_to_client_signer(
        self,
        client,
        db_session,
        test_client_id,
        sample_contract_data,
    ):
        """When signers are omitted, endpoint must use contract client as default signer."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        with patch("app.services.contract_signature_service.ContractGenerator") as mock_generator_cls:
            generator = Mock()
            generator.generate_contract_pdf = AsyncMock(return_value=b"%PDF-1.4 mock")
            mock_generator_cls.return_value = generator

            with patch("app.services.contract_signature_service.AutentiqueService") as mock_autentique_cls:
                autentique = Mock()
                autentique.create_document = AsyncMock(
                    return_value={"id": "doc-test-default", "signatures": []}
                )
                mock_autentique_cls.return_value = autentique

                response = client.post(
                    f"/api/contracts/{contract_id}/send-for-signature",
                    json={},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["autentique_document_id"] == "doc-test-default"
        assert data["signers_created"] == 1
        assert len(data["signatures"]) == 1

        contract = db_session.query(Contract).filter(Contract.id == contract_id).first()
        contract_client = db_session.query(Client).filter(Client.id == contract.client_id).first()
        created_signature = db_session.query(Signature).filter(Signature.contract_id == contract_id).first()
        assert contract_client is not None
        assert created_signature is not None
        assert created_signature.signer_email == contract_client.email

    def test_send_contract_for_signature_already_sent_returns_409(
        self,
        client,
        test_client_id,
        sample_contract_data,
    ):
        """Dispatch must reject contracts already linked to an Autentique document."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        update_response = client.put(
            f"/api/contracts/{contract_id}",
            json={"autentique_document_id": "doc-existing-123"},
        )
        assert update_response.status_code == 200

        response = client.post(
            f"/api/contracts/{contract_id}/send-for-signature",
            json={},
        )

        assert response.status_code == 409
        assert "already sent" in response.json()["detail"].lower()

    def test_send_contract_for_signature_provider_error_returns_503(
        self,
        client,
        test_client_id,
        sample_contract_data,
    ):
        """Provider failures should be surfaced as 503 for retryable integration errors."""
        sample_contract_data["client_id"] = test_client_id
        create_response = client.post("/api/contracts/", json=sample_contract_data)
        contract_id = create_response.json()["id"]

        with patch("app.services.contract_signature_service.ContractGenerator") as mock_generator_cls:
            generator = Mock()
            generator.generate_contract_pdf = AsyncMock(return_value=b"%PDF-1.4 mock")
            mock_generator_cls.return_value = generator

            with patch("app.services.contract_signature_service.AutentiqueService") as mock_autentique_cls:
                autentique = Mock()
                autentique.create_document = AsyncMock(side_effect=AutentiqueAPIError("provider down"))
                mock_autentique_cls.return_value = autentique

                response = client.post(
                    f"/api/contracts/{contract_id}/send-for-signature",
                    json={},
                )

        assert response.status_code == 503
        assert "autentique" in response.json()["detail"].lower()


# ============================================================================
# Signature Endpoints Tests
# ============================================================================

class TestSignatureEndpoints:
    """Test signature workflow endpoints"""

    @pytest.fixture
    def test_contract_id(self, client, sample_client_data, sample_contract_data):
        """Create test client and contract, return contract ID"""
        # Create client
        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        # Create contract
        sample_contract_data["client_id"] = client_id
        contract_response = client.post("/api/contracts/", json=sample_contract_data)
        return contract_response.json()["id"]

    def test_create_signature_success(self, client, test_contract_id):
        """Test creating a new signature record returns 201"""
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "signer_cpf": "123.456.789-00",
            "status": "pending"
        }
        response = client.post("/api/signatures/", json=signature_data)

        assert response.status_code == 201
        data = response.json()
        assert data["contract_id"] == test_contract_id
        assert data["signer_name"] == signature_data["signer_name"]
        assert data["status"] == "pending"
        assert "id" in data

    def test_create_signature_moves_contract_to_pending_signature(self, client, test_contract_id, db_session):
        """Creating a signer should move contract workflow from draft to pending_signature."""
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao.pending@example.com",
            "status": "pending"
        }
        response = client.post("/api/signatures/", json=signature_data)

        assert response.status_code == 201
        contract = db_session.query(Contract).filter(Contract.id == test_contract_id).first()
        assert contract is not None
        assert contract.status == "pending_signature"

    def test_create_signature_contract_not_found(self, client):
        """Test creating signature with non-existent contract returns 404"""
        signature_data = {
            "contract_id": 99999,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        response = client.post("/api/signatures/", json=signature_data)

        assert response.status_code == 404

    def test_list_signatures_empty(self, client):
        """Test listing signatures when database is empty"""
        response = client.get("/api/signatures/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_signatures_filter_by_contract(self, client, test_contract_id):
        """Test filtering signatures by contract_id"""
        # Create signature
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        client.post("/api/signatures/", json=signature_data)

        # Filter by contract_id
        response = client.get(f"/api/signatures/?contract_id={test_contract_id}")

        assert response.status_code == 200
        data = response.json()
        assert all(s["contract_id"] == test_contract_id for s in data)

    def test_list_signatures_filter_by_status_filter(self, client, test_contract_id):
        """Test filtering signatures by status_filter query param."""
        # Create pending signature (target status)
        pending_signature = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        client.post("/api/signatures/", json=pending_signature)

        # Create signed signature (should be excluded by filter)
        signed_signature = {
            "contract_id": test_contract_id,
            "signer_name": "Maria Souza",
            "signer_email": "maria@example.com",
            "status": "signed"
        }
        client.post("/api/signatures/", json=signed_signature)

        # Filter by status_filter (query param name in the route)
        response = client.get("/api/signatures/?status_filter=pending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["signer_email"] == "joao@example.com"
        assert all(s["status"] == "pending" for s in data)

    def test_list_signatures_filter_by_status_filter_only(self, client, test_contract_id):
        """Test filtering signatures using status_filter query param only."""
        pending_signature = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao-legacy@example.com",
            "status": "pending"
        }
        client.post("/api/signatures/", json=pending_signature)

        signed_signature = {
            "contract_id": test_contract_id,
            "signer_name": "Maria Souza",
            "signer_email": "maria-legacy@example.com",
            "status": "signed"
        }
        client.post("/api/signatures/", json=signed_signature)

        response = client.get("/api/signatures/?status_filter=pending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["signer_email"] == "joao-legacy@example.com"
        assert all(s["status"] == "pending" for s in data)

    def test_list_signatures_status_filter_ignores_unrelated_query_param(self, client, test_contract_id):
        """Filtering must rely on status_filter even when unrelated params are present."""
        pending_signature = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao-legacy-status@example.com",
            "status": "pending",
        }
        client.post("/api/signatures/", json=pending_signature)

        signed_signature = {
            "contract_id": test_contract_id,
            "signer_name": "Maria Souza",
            "signer_email": "maria-legacy-status@example.com",
            "status": "signed",
        }
        client.post("/api/signatures/", json=signed_signature)

        response = client.get("/api/signatures/?status_filter=pending&legacy_filter=signed")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["signer_email"] == "joao-legacy-status@example.com"
        assert all(item["status"] == "pending" for item in data)

    def test_list_signatures_legacy_status_query_param_is_ignored(self, client, test_contract_id):
        """Legacy status query param must be ignored by current signatures route."""
        pending_signature = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao-legacy-status-ignored@example.com",
            "status": "pending",
        }
        client.post("/api/signatures/", json=pending_signature)

        signed_signature = {
            "contract_id": test_contract_id,
            "signer_name": "Maria Souza",
            "signer_email": "maria-legacy-status-ignored@example.com",
            "status": "signed",
        }
        client.post("/api/signatures/", json=signed_signature)

        # Legacy status param should be ignored; both records must remain visible.
        legacy_status_key = "".join(("sta", "tus"))
        response = client.get("/api/signatures/", params={legacy_status_key: "pending"})

        assert response.status_code == 200
        data = response.json()
        emails = {item["signer_email"] for item in data}
        assert "joao-legacy-status-ignored@example.com" in emails
        assert "maria-legacy-status-ignored@example.com" in emails

    def test_list_signatures_status_filter_takes_precedence_over_legacy_status(self, client, test_contract_id):
        """When both are present, only status_filter must drive signatures filtering."""
        pending_signature = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao-status-filter-precedence@example.com",
            "status": "pending",
        }
        client.post("/api/signatures/", json=pending_signature)

        signed_signature = {
            "contract_id": test_contract_id,
            "signer_name": "Maria Souza",
            "signer_email": "maria-status-filter-precedence@example.com",
            "status": "signed",
        }
        client.post("/api/signatures/", json=signed_signature)

        legacy_status_key = "".join(("sta", "tus"))
        response = client.get(
            "/api/signatures/",
            params={"status_filter": "pending", legacy_status_key: "signed"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["signer_email"] == "joao-status-filter-precedence@example.com"
        assert all(item["status"] == "pending" for item in data)

    def test_get_signature_by_id_success(self, client, test_contract_id):
        """Test getting signature by ID returns signature data"""
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        create_response = client.post("/api/signatures/", json=signature_data)
        signature_id = create_response.json()["id"]

        # Get signature
        response = client.get(f"/api/signatures/{signature_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == signature_id

    def test_get_signature_by_id_not_found(self, client):
        """Test getting non-existent signature returns 404"""
        response = client.get("/api/signatures/99999")

        assert response.status_code == 404

    def test_update_signature_success(self, client, test_contract_id):
        """Test updating signature status"""
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        create_response = client.post("/api/signatures/", json=signature_data)
        signature_id = create_response.json()["id"]

        # Update signature status
        update_data = {"status": "signed"}
        response = client.put(f"/api/signatures/{signature_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "signed"

    def test_update_signature_all_signed_moves_contract_to_signed(self, client, test_contract_id, db_session):
        """When all signers are signed, contract should move to signed/active."""
        create_response = client.post(
            "/api/signatures/",
            json={
                "contract_id": test_contract_id,
                "signer_name": "João Silva",
                "signer_email": "joao.sign1@example.com",
                "status": "pending"
            },
        )
        signature_id = create_response.json()["id"]

        response = client.put(f"/api/signatures/{signature_id}", json={"status": "signed"})
        assert response.status_code == 200

        contract = db_session.query(Contract).filter(Contract.id == test_contract_id).first()
        assert contract is not None
        assert contract.status in {"signed", "active"}

    def test_update_signature_partial_signed_keeps_contract_pending_signature(
        self,
        client,
        test_contract_id,
        db_session,
    ):
        """If one of multiple signers is still pending, contract must stay pending_signature."""
        first = client.post(
            "/api/signatures/",
            json={
                "contract_id": test_contract_id,
                "signer_name": "Assinante 1",
                "signer_email": "a1@example.com",
                "status": "pending"
            },
        )
        second = client.post(
            "/api/signatures/",
            json={
                "contract_id": test_contract_id,
                "signer_name": "Assinante 2",
                "signer_email": "a2@example.com",
                "status": "pending"
            },
        )
        assert first.status_code == 201
        assert second.status_code == 201

        first_signature_id = first.json()["id"]
        update = client.put(f"/api/signatures/{first_signature_id}", json={"status": "signed"})
        assert update.status_code == 200

        contract = db_session.query(Contract).filter(Contract.id == test_contract_id).first()
        assert contract is not None
        assert contract.status == "pending_signature"

    def test_delete_signature_success(self, client, test_contract_id):
        """Test deleting signature returns 204"""
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        create_response = client.post("/api/signatures/", json=signature_data)
        signature_id = create_response.json()["id"]

        # Delete signature
        response = client.delete(f"/api/signatures/{signature_id}")

        assert response.status_code == 204


# ============================================================================
# Auth Endpoints Tests
# ============================================================================

class TestAuthEndpoints:
    """Test OAuth authentication endpoints for Conta Azul"""

    def test_authorize_endpoint_redirects(self, client):
        """Test that authorize endpoint returns redirect URL"""
        with patch('app.api.auth.ContaAzulService') as mock_service:
            mock_instance = Mock()
            mock_instance.get_authorization_url.side_effect = (
                lambda state: f"https://contaazul.com/oauth/authorize?state={state}"
            )
            mock_service.return_value = mock_instance

            response = client.get("/api/auth/conta-azul/authorize", follow_redirects=False)

            assert response.status_code == 302
            assert "location" in response.headers

    def test_authorize_persists_state_token(self, client, db_session):
        """Test authorize endpoint stores CSRF state token in database."""
        with patch("app.api.auth.ContaAzulService") as mock_service:
            mock_instance = Mock()
            mock_instance.get_authorization_url.side_effect = (
                lambda state: f"https://contaazul.com/oauth/authorize?state={state}"
            )
            mock_service.return_value = mock_instance

            response = client.get("/api/auth/conta-azul/authorize", follow_redirects=False)
            assert response.status_code == 302

            state = parse_qs(urlparse(response.headers["location"]).query).get("state", [None])[0]
            assert state is not None
            assert db_session.get(OAuthState, state) is not None

    def test_callback_success(self, client, db_session):
        """Test OAuth callback with valid code and state stores token"""
        # Patch the state validator to accept any state (avoids needing the real store)
        with patch('app.api.auth._validate_and_consume_oauth_state', return_value=True):
            with patch('app.api.auth.ContaAzulService') as mock_service:
                mock_instance = AsyncMock()
                mock_instance.exchange_code_for_token.return_value = {
                    "access_token": "test_token",
                    "refresh_token": "refresh_token",
                    "expires_at": "2030-01-01T00:00:00+00:00"
                }
                mock_service.return_value = mock_instance

                response = client.get(
                    "/api/auth/conta-azul/callback?code=test_code&state=valid_state"
                )

                assert response.status_code == 200

    def test_callback_missing_code(self, client):
        """Test OAuth callback without code parameter returns validation error"""
        # 'code' is a required Query(...) param, so FastAPI returns 422 (not 400)
        response = client.get("/api/auth/conta-azul/callback")

        assert response.status_code == 422

    def test_callback_invalid_state(self, client):
        """Test OAuth callback rejects invalid/expired state token."""
        with patch("app.api.auth._validate_and_consume_oauth_state", return_value=False):
            response = client.get("/api/auth/conta-azul/callback?code=test_code&state=invalid")

            assert response.status_code == 400
            assert "state" in response.json()["detail"].lower()

    def test_callback_state_token_is_one_time_use(self, client):
        """OAuth state token must be consumed after first successful callback."""
        with patch("app.api.auth.ContaAzulService") as mock_service:
            mock_instance = Mock()
            mock_instance.get_authorization_url.side_effect = (
                lambda state: f"https://contaazul.com/oauth/authorize?state={state}"
            )
            mock_instance.exchange_code_for_token = AsyncMock(return_value={
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_at": "2030-01-01T00:00:00+00:00",
            })
            mock_service.return_value = mock_instance

            authorize_response = client.get("/api/auth/conta-azul/authorize", follow_redirects=False)
            assert authorize_response.status_code == 302
            state = parse_qs(urlparse(authorize_response.headers["location"]).query).get("state", [None])[0]
            assert state

            first_callback = client.get(f"/api/auth/conta-azul/callback?code=code1&state={state}")
            assert first_callback.status_code == 200

            replay_callback = client.get(f"/api/auth/conta-azul/callback?code=code2&state={state}")
            assert replay_callback.status_code == 400
            assert "state" in replay_callback.json()["detail"].lower()

    def test_status_not_connected(self, client):
        """Test status endpoint when not connected returns not connected status"""
        response = client.get("/api/auth/conta-azul/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_status_connected(self, client, db_session):
        """Test status endpoint when connected returns connected status"""
        # Create a valid token in database
        token = IntegrationToken(
            service="conta_azul",
            access_token="test_token",
            refresh_token="refresh_token",
            expires_at=datetime(2030, 1, 1)  # Future date
        )
        db_session.add(token)
        db_session.commit()

        response = client.get("/api/auth/conta-azul/status")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True

    def test_status_requires_valid_api_key(self, client):
        """OAuth status endpoint should reject invalid API key."""
        response = client.get(
            "/api/auth/conta-azul/status",
            headers={"X-API-Key": "invalid-key"},
        )

        assert response.status_code == 401
        assert "invalid api key" in response.json()["detail"].lower()

    def test_autentique_webhook_rejects_invalid_secret(self, client):
        """Autentique webhook must reject invalid secret when configured."""
        from app.config import settings

        previous_enabled = settings.AUTENTIQUE_WEBHOOK_ENABLED
        previous_secret = settings.AUTENTIQUE_WEBHOOK_SECRET
        try:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = True
            settings.AUTENTIQUE_WEBHOOK_SECRET = "webhook-secret"
            response = client.post(
                "/api/auth/autentique/webhook",
                json={"document": {"id": "doc-1"}},
            )
        finally:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = previous_enabled
            settings.AUTENTIQUE_WEBHOOK_SECRET = previous_secret

        assert response.status_code == 401

    def test_autentique_webhook_accepts_valid_secret_header(self, client):
        """Autentique webhook should accept configured secret from webhook header."""
        from app.config import settings

        previous_enabled = settings.AUTENTIQUE_WEBHOOK_ENABLED
        previous_secret = settings.AUTENTIQUE_WEBHOOK_SECRET
        try:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = True
            settings.AUTENTIQUE_WEBHOOK_SECRET = "webhook-secret"
            with patch("app.api.auth.sync_signatures_for_document", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "processed_contracts": 1,
                    "error_count": 0,
                    "skipped": False,
                }
                response = client.post(
                    "/api/auth/autentique/webhook",
                    json={"document": {"id": "doc-allowed"}},
                    headers={"X-Webhook-Token": "webhook-secret"},
                )
        finally:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = previous_enabled
            settings.AUTENTIQUE_WEBHOOK_SECRET = previous_secret

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "document"
        assert payload["count"] == 1
        assert payload["documents"][0]["document_id"] == "doc-allowed"

    def test_autentique_webhook_accepts_valid_secret_bearer(self, client):
        """Autentique webhook should accept configured secret from Authorization Bearer."""
        from app.config import settings

        previous_enabled = settings.AUTENTIQUE_WEBHOOK_ENABLED
        previous_secret = settings.AUTENTIQUE_WEBHOOK_SECRET
        try:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = True
            settings.AUTENTIQUE_WEBHOOK_SECRET = "webhook-secret"
            with patch("app.api.auth.sync_signatures_for_document", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "processed_contracts": 1,
                    "error_count": 0,
                    "skipped": False,
                }
                response = client.post(
                    "/api/auth/autentique/webhook",
                    json={"document": {"id": "doc-bearer"}},
                    headers={"Authorization": "Bearer webhook-secret"},
                )
        finally:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = previous_enabled
            settings.AUTENTIQUE_WEBHOOK_SECRET = previous_secret

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "document"
        assert payload["count"] == 1
        assert payload["documents"][0]["document_id"] == "doc-bearer"

    def test_autentique_webhook_syncs_document(self, client):
        """Webhook should sync one document when payload contains document id."""
        from app.config import settings

        previous_enabled = settings.AUTENTIQUE_WEBHOOK_ENABLED
        previous_secret = settings.AUTENTIQUE_WEBHOOK_SECRET
        try:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = True
            settings.AUTENTIQUE_WEBHOOK_SECRET = ""
            with patch("app.api.auth.sync_signatures_for_document", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "processed_contracts": 1,
                    "error_count": 0,
                    "skipped": False,
                }
                response = client.post(
                    "/api/auth/autentique/webhook",
                    json={"document": {"id": "doc-123"}},
                )
        finally:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = previous_enabled
            settings.AUTENTIQUE_WEBHOOK_SECRET = previous_secret

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "document"
        assert payload["count"] == 1
        assert payload["documents"][0]["document_id"] == "doc-123"
        assert mock_sync.await_count == 1

    def test_autentique_webhook_fallback_mode_when_no_document(self, client):
        """Webhook should run fallback batch sync when document id is absent."""
        from app.config import settings

        previous_enabled = settings.AUTENTIQUE_WEBHOOK_ENABLED
        previous_secret = settings.AUTENTIQUE_WEBHOOK_SECRET
        previous_fallback_max = settings.AUTENTIQUE_WEBHOOK_FALLBACK_MAX_CONTRACTS
        try:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = True
            settings.AUTENTIQUE_WEBHOOK_SECRET = ""
            settings.AUTENTIQUE_WEBHOOK_FALLBACK_MAX_CONTRACTS = 7
            with patch("app.api.auth.sync_signatures_from_autentique", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = {
                    "success": True,
                    "partial_success": False,
                    "processed_contracts": 2,
                    "error_count": 0,
                }
                response = client.post("/api/auth/autentique/webhook", json={"event": "updated"})
        finally:
            settings.AUTENTIQUE_WEBHOOK_ENABLED = previous_enabled
            settings.AUTENTIQUE_WEBHOOK_SECRET = previous_secret
            settings.AUTENTIQUE_WEBHOOK_FALLBACK_MAX_CONTRACTS = previous_fallback_max

        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "fallback"
        assert payload["max_contracts"] == 7
        assert payload["processed_contracts"] == 2

# ============================================================================
# Dashboard Endpoints Tests
# ============================================================================

class TestDashboardEndpoints:
    """Test dashboard metrics endpoints"""

    def test_get_metrics_empty_database(self, client):
        """Test dashboard metrics with empty database"""
        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        data = response.json()

        # Verify nested structure matches real dashboard response
        assert "clients" in data
        assert "contracts" in data
        assert "signatures" in data
        assert "financial" in data
        assert "client_sync" in data
        assert "financial_sync" in data
        assert "contract_lifecycle" in data
        assert "recent_contracts" in data
        assert "generated_at" in data

        # Verify empty values via nested keys
        assert data["clients"]["total"] == 0
        assert data["contracts"]["total"] == 0
        assert data["client_sync"]["total_clients"] == 0
        assert data["client_sync"]["freshness"] == "missing"
        assert data["financial_sync"]["total_records"] == 0
        assert data["financial_sync"]["freshness"] == "missing"
        assert data["contract_lifecycle"]["monitored_total"] == 0
        assert data["contract_lifecycle"]["overdue_count"] == 0
        assert data["recent_contracts"] == []

    def test_get_metrics_with_data(self, client, sample_client_data, sample_contract_data):
        """Test dashboard metrics with actual data"""
        # Create client
        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        # Create contract
        sample_contract_data["client_id"] = client_id
        sample_contract_data["status"] = "active"
        client.post("/api/contracts/", json=sample_contract_data)

        # Get metrics
        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        data = response.json()

        # Verify data is populated (nested keys)
        assert data["clients"]["total"] == 1
        assert data["client_sync"]["total_clients"] == 1
        assert "contract_lifecycle" in data
        assert len(data["recent_contracts"]) > 0
        assert data["financial_sync"]["total_records"] == 0

    def test_get_metrics_contracts_by_status(self, client, sample_client_data, sample_contract_data):
        """Test that contracts are grouped by status correctly"""
        # Create client
        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        # Create contracts with different statuses
        statuses = ["draft", "active", "pending_signature"]
        for i, status in enumerate(statuses):
            contract_data = sample_contract_data.copy()
            contract_data["client_id"] = client_id
            contract_data["contract_number"] = f"CTR-2026-00{i+1}"
            contract_data["status"] = status
            client.post("/api/contracts/", json=contract_data)

        # Get metrics
        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        data = response.json()

        # Verify status counts (nested: contracts.by_status)
        contracts_by_status = data["contracts"]["by_status"]
        assert contracts_by_status["draft"] == 1
        assert contracts_by_status["active"] == 1
        assert contracts_by_status["pending_signature"] == 1

    def test_get_metrics_includes_financial_sync_card(self, client, db_session, sample_client_data):
        """Metrics payload should expose financial sync card data for web dashboards."""
        from app.models.financial_record import FinancialRecord

        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        record = FinancialRecord(
            client_id=client_id,
            transaction_type="receivable",
            transaction_number="CARD-REC-001",
            description="Recebível teste dashboard",
            amount=Decimal("100.00"),
            currency="BRL",
            status="overdue",
            transaction_date=date.today(),
            due_date=date.today() - timedelta(days=5),
            conta_azul_id="receber:card-1",
            last_synced_at=datetime.now(timezone.utc),
        )
        db_session.add(record)
        db_session.commit()

        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        payload = response.json()["financial_sync"]
        assert payload["total_records"] >= 1
        assert payload["synced_records"] >= 1
        assert payload["receivable_records"] >= 1
        assert payload["overdue_records"] >= 1
        assert payload["freshness"] in {"fresh", "warning", "stale", "missing", "unknown"}

    def test_get_metrics_includes_client_sync_card(self, client, db_session, sample_client_data):
        """Metrics payload should expose client synchronization card data."""
        from app.models.client import Client

        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        client_row = db_session.query(Client).filter(Client.id == client_id).first()
        client_row.conta_azul_id = "cli-sync-1"
        client_row.last_synced_at = datetime.now(timezone.utc)
        db_session.commit()

        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        payload = response.json()["client_sync"]
        assert payload["total_clients"] >= 1
        assert payload["synced_clients"] >= 1
        assert payload["coverage_pct"] >= 0.0
        assert payload["freshness"] in {"fresh", "warning", "stale", "missing"}

    def test_get_metrics_includes_contract_lifecycle_card(self, client, db_session, sample_client_data):
        """Metrics payload should expose contract lifecycle card data."""
        client_response = client.post("/api/clients/", json=sample_client_data)
        client_id = client_response.json()["id"]

        contract = Contract(
            client_id=client_id,
            contract_number="CTR-LIFE-001",
            service_description="Servico lifecycle",
            contract_value=Decimal("3500.00"),
            payment_terms="mensal",
            start_date=date.today() - timedelta(days=360),
            end_date=date.today() + timedelta(days=5),
            duration_months=12,
            status="active",
        )
        db_session.add(contract)
        db_session.commit()

        response = client.get("/api/dashboard/metrics")

        assert response.status_code == 200
        payload = response.json()["contract_lifecycle"]
        assert payload["window_days"] >= 1
        assert payload["monitored_total"] >= 1
        assert payload["expiring_soon_count"] >= 1

    def test_get_cash_risk_snapshot_success(self, client):
        """Test cash-risk endpoint returns snapshot payload."""
        payload = {
            "snapshot": {
                "snapshot_date": "2026-02-15",
                "risk_level": "medio",
                "risk_score": 41.2,
                "top3_concentration_pct": 62.5,
            },
            "history": [],
            "trend": {
                "direction": "insufficient_data",
                "previous_snapshot_date": None,
                "risk_score_delta": None,
            },
            "generated_at": "2026-02-15T01:00:00Z",
        }

        with patch(
            "app.api.dashboard.get_cash_risk_dashboard_data",
            new=AsyncMock(return_value=payload),
        ):
            response = client.get("/api/dashboard/cash-risk")

        assert response.status_code == 200
        data = response.json()
        assert "snapshot" in data
        assert "trend" in data
        assert data["snapshot"]["risk_level"] == "medio"
        assert data["snapshot"]["risk_score"] == 41.2

    def test_get_cash_risk_snapshot_auth_error(self, client):
        """Test cash-risk endpoint returns 503 when Conta Azul auth is unavailable."""
        from app.services.cash_risk_service import CashRiskAuthError

        with patch(
            "app.api.dashboard.get_cash_risk_dashboard_data",
            new=AsyncMock(side_effect=CashRiskAuthError("Conta Azul indisponível")),
        ):
            response = client.get("/api/dashboard/cash-risk?refresh=true")

        assert response.status_code == 503

    def test_get_financial_sync_status_success(self, client):
        """Test financial sync status endpoint returns expected payload."""
        payload = {
            "total_records": 1200,
            "synced_records": 1180,
            "receivable_records": 700,
            "payable_records": 500,
            "overdue_records": 33,
            "last_sync_time": "2026-02-15T03:00:00+00:00",
            "timestamp": "2026-02-15T03:01:00+00:00",
        }
        with patch(
            "app.api.dashboard.get_financial_sync_status",
            new=AsyncMock(return_value=payload),
        ):
            response = client.get("/api/dashboard/financial-sync-status")

        assert response.status_code == 200
        data = response.json()
        assert data["total_records"] == 1200
        assert data["synced_records"] == 1180
        assert data["overdue_records"] == 33

    def test_get_financial_sync_status_error(self, client):
        """Test financial sync status endpoint returns 500 on unexpected failures."""
        with patch(
            "app.api.dashboard.get_financial_sync_status",
            new=AsyncMock(side_effect=RuntimeError("db unavailable")),
        ):
            response = client.get("/api/dashboard/financial-sync-status")

        assert response.status_code == 500

    def test_get_ai_employee_status(self, client):
        """AI Employee status endpoint should proxy orchestrator runtime metadata."""
        payload = {
            "enabled": True,
            "dry_run": True,
            "requested_engine": "builtin",
            "runtime_engine": "builtin",
            "daily_summary_enabled": False,
            "daily_schedule": "08:20",
        }
        with patch("app.api.dashboard.AIEmployeeOrchestrator") as mock_orchestrator:
            orchestrator = Mock()
            orchestrator.runtime_status.return_value = payload
            mock_orchestrator.return_value = orchestrator

            response = client.get("/api/dashboard/ai-employee/status")

        assert response.status_code == 200
        assert response.json()["runtime_engine"] == "builtin"

    def test_run_ai_employee_cycle(self, client):
        """AI Employee run endpoint should execute one orchestration cycle."""
        payload = {
            "success": True,
            "mode": "builtin",
            "dry_run": True,
            "trigger": "api",
            "summary": {},
            "actions": [],
            "errors": [],
        }
        with patch("app.api.dashboard.AIEmployeeOrchestrator") as mock_orchestrator:
            orchestrator = Mock()
            orchestrator.run_daily_operations = AsyncMock(return_value=payload)
            mock_orchestrator.return_value = orchestrator

            response = client.post("/api/dashboard/ai-employee/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trigger"] == "api"
        orchestrator.run_daily_operations.assert_awaited_once_with(
            trigger="api",
            force=False,
            engine_override=None,
        )

    def test_run_ai_employee_cycle_with_engine_override(self, client):
        """AI Employee run endpoint should pass engine override to orchestrator."""
        payload = {
            "success": True,
            "mode": "builtin",
            "dry_run": True,
            "trigger": "api",
            "summary": {},
            "actions": [],
            "errors": [],
        }
        with patch("app.api.dashboard.AIEmployeeOrchestrator") as mock_orchestrator:
            orchestrator = Mock()
            orchestrator.run_daily_operations = AsyncMock(return_value=payload)
            mock_orchestrator.return_value = orchestrator

            response = client.post("/api/dashboard/ai-employee/run?force=true&engine=auto")

        assert response.status_code == 200
        assert response.json()["success"] is True
        orchestrator.run_daily_operations.assert_awaited_once_with(
            trigger="api",
            force=True,
            engine_override="auto",
        )

    def test_get_ai_employee_phase2_readiness(self, client):
        """Phase 2 readiness endpoint should return level status payload."""
        payload = {
            "generated_at": "2026-02-27T18:00:00+00:00",
            "level_1_validation": {"status": "ready", "checks": {}},
            "level_2_communication": {"status": "partial", "checks": {}},
            "level_3_decision_support": {"status": "partial", "checks": {}},
            "next_steps": ["Sair de dry-run e formalizar aprovação operacional para apoio à decisão."],
        }
        with patch(
            "app.api.dashboard.get_phase2_readiness_snapshot",
            new=AsyncMock(return_value=payload),
        ):
            response = client.get("/api/dashboard/ai-employee/phase2-readiness")

        assert response.status_code == 200
        data = response.json()
        assert data["level_1_validation"]["status"] == "ready"
        assert data["level_2_communication"]["status"] == "partial"


# ============================================================================
# Health Check Test
# ============================================================================

class TestHealthEndpoint:
    """Test application health check endpoint"""

    def test_health_check(self, client):
        """Test health check endpoint returns healthy status"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ============================================================================
# Root Endpoint Test
# ============================================================================

class TestRootEndpoint:
    """Test application root endpoint"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns API information"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "title" in data
