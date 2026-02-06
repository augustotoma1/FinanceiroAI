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
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, date
from decimal import Decimal

from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.models.integration_token import IntegrationToken


# ============================================================================
# Conversation Endpoints Tests
# ============================================================================

class TestConversationEndpoints:
    """Test conversational AI endpoints"""

    def test_start_conversation_success(self, client):
        """Test starting a new conversation returns conversation ID and greeting"""
        # Mock Claude service
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = Mock()
            mock_service.send_message.return_value = {
                "message": "Hello! I'll help you create a service contract."
            }
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
        # First, start a conversation
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = Mock()
            mock_service.send_message.return_value = {
                "message": "Hello! I'll help you create a service contract."
            }
            mock_claude.return_value = mock_service

            start_response = client.post("/api/conversation/start")
            conversation_id = start_response.json()["conversation_id"]

            # Mock continuing conversation
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
        with patch('app.api.conversation.ClaudeService'):
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
            mock_service = Mock()
            mock_service.send_message.return_value = {
                "message": "Hello! I'll help you create a service contract."
            }
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

    def test_delete_conversation_success(self, client):
        """Test deleting a conversation"""
        with patch('app.api.conversation.ClaudeService') as mock_claude:
            mock_service = Mock()
            mock_service.send_message.return_value = {
                "message": "Hello!"
            }
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
            mock_service = Mock()
            mock_service.send_message.return_value = {
                "message": "Hello!"
            }
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

    def test_list_contracts_filter_by_status(self, client, test_client_id, sample_contract_data):
        """Test filtering contracts by status"""
        sample_contract_data["client_id"] = test_client_id
        sample_contract_data["status"] = "draft"
        client.post("/api/contracts/", json=sample_contract_data)

        # Filter by status
        response = client.get("/api/contracts/?status=draft")

        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "draft" for c in data)

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

    def test_list_signatures_filter_by_status(self, client, test_contract_id):
        """Test filtering signatures by status"""
        # Create signature
        signature_data = {
            "contract_id": test_contract_id,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "status": "pending"
        }
        client.post("/api/signatures/", json=signature_data)

        # Filter by status
        response = client.get("/api/signatures/?status=pending")

        assert response.status_code == 200
        data = response.json()
        assert all(s["status"] == "pending" for s in data)

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
        with patch('app.services.conta_azul_service.ContaAzulService') as mock_service:
            mock_instance = Mock()
            mock_instance.get_authorization_url.return_value = "https://contaazul.com/oauth/authorize?..."
            mock_service.return_value = mock_instance

            response = client.get("/api/auth/conta-azul/authorize", follow_redirects=False)

            assert response.status_code == 302
            assert "location" in response.headers

    def test_callback_success(self, client, db_session):
        """Test OAuth callback with valid code stores token"""
        with patch('app.services.conta_azul_service.ContaAzulService') as mock_service:
            mock_instance = Mock()
            mock_instance.exchange_code_for_token.return_value = {
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "expires_in": 3600
            }
            mock_service.return_value = mock_instance

            response = client.get("/api/auth/conta-azul/callback?code=test_code")

            assert response.status_code in [200, 302]  # Could be redirect or success message

    def test_callback_missing_code(self, client):
        """Test OAuth callback without code parameter returns error"""
        response = client.get("/api/auth/conta-azul/callback")

        assert response.status_code == 400

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

        # Verify structure
        assert "total_clients" in data
        assert "contracts_by_status" in data
        assert "signatures" in data
        assert "financial" in data
        assert "recent_contracts" in data

        # Verify empty values
        assert data["total_clients"] == 0
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

        # Verify data is populated
        assert data["total_clients"] == 1
        assert len(data["recent_contracts"]) > 0

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

        # Verify status counts
        contracts_by_status = data["contracts_by_status"]
        assert contracts_by_status["draft"] == 1
        assert contracts_by_status["active"] == 1
        assert contracts_by_status["pending_signature"] == 1


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
