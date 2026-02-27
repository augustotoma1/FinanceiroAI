"""
Unit tests for Autentique API Service

Tests cover:
- Service initialization and configuration
- Rate limiting enforcement
- Document creation workflow
- Document status tracking
- Document listing with pagination
- Helper methods for signature checking
- Error handling and API failures
- Edge cases and GraphQL transport errors
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone
from gql.transport.exceptions import TransportError

from app.services.autentique_service import (
    AutentiqueService,
    AutentiqueError,
    AutentiqueRateLimitError,
    AutentiqueAPIError
)
from app.config import settings


class TestAutentiqueServiceInitialization:
    """Test Autentique service initialization and configuration"""

    def test_initialization_success(self):
        """Test successful service initialization with valid configuration"""
        with patch('app.services.autentique_service.Client') as mock_client:
            service = AutentiqueService()

            assert service.client is not None
            assert service.api_url == settings.AUTENTIQUE_API_URL
            assert service.api_key == settings.AUTENTIQUE_API_KEY
            assert service.rate_limit == settings.AUTENTIQUE_RATE_LIMIT
            assert len(service.request_timestamps) == 0
            mock_client.assert_called_once()

    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key"""
        with patch('app.config.settings.AUTENTIQUE_API_KEY', None):
            with pytest.raises(ValueError, match="Autentique API initialization failed"):
                AutentiqueService()

    def test_initialization_without_api_url(self):
        """Test that initialization fails without API URL"""
        with patch('app.config.settings.AUTENTIQUE_API_URL', None):
            with pytest.raises(ValueError, match="Autentique API initialization failed"):
                AutentiqueService()

    def test_initialization_configures_transport_correctly(self):
        """Test that GraphQL transport is configured with correct headers"""
        with patch('app.services.autentique_service.RequestsHTTPTransport') as mock_transport:
            with patch('app.services.autentique_service.Client'):
                service = AutentiqueService()

                mock_transport.assert_called_once()
                call_kwargs = mock_transport.call_args[1]
                assert call_kwargs['url'] == settings.AUTENTIQUE_API_URL
                assert 'Authorization' in call_kwargs['headers']
                assert call_kwargs['headers']['Authorization'] == f"Bearer {settings.AUTENTIQUE_API_KEY}"
                assert call_kwargs['verify'] is True
                assert call_kwargs['retries'] == 3
                assert call_kwargs['timeout'] == 30


class TestRateLimiting:
    """Test rate limiting enforcement"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            return AutentiqueService()

    @pytest.mark.asyncio
    async def test_rate_limit_allows_requests_under_limit(self, service):
        """Test that requests under rate limit are allowed immediately"""
        # Add some timestamps within the window
        now = datetime.now(timezone.utc)
        service.request_timestamps.extend([
            now - timedelta(seconds=30),
            now - timedelta(seconds=20),
            now - timedelta(seconds=10)
        ])

        # This should not wait
        await service._wait_for_rate_limit()

        # Should add new timestamp
        assert len(service.request_timestamps) == 4

    @pytest.mark.asyncio
    async def test_rate_limit_removes_old_timestamps(self, service):
        """Test that timestamps older than 1 minute are removed"""
        now = datetime.now(timezone.utc)
        service.request_timestamps.extend([
            now - timedelta(minutes=2),
            now - timedelta(minutes=1, seconds=30),
            now - timedelta(seconds=30)
        ])

        await service._wait_for_rate_limit()

        # Old timestamps should be removed
        assert len(service.request_timestamps) == 2

    @pytest.mark.asyncio
    async def test_rate_limit_enforces_wait_when_limit_reached(self, service):
        """Test that rate limiting waits when limit is reached"""
        # Fill up to rate limit
        now = datetime.now(timezone.utc)
        oldest_timestamp = now - timedelta(seconds=30)

        service.request_timestamps.extend([
            oldest_timestamp + timedelta(seconds=i)
            for i in range(service.rate_limit)
        ])

        # Mock asyncio.sleep to avoid actual waiting
        with patch('asyncio.sleep') as mock_sleep:
            await service._wait_for_rate_limit()

            # Should have called sleep
            mock_sleep.assert_called_once()
            wait_time = mock_sleep.call_args[0][0]
            assert wait_time > 0

    @pytest.mark.asyncio
    async def test_rate_limit_adds_timestamp_after_check(self, service):
        """Test that current request timestamp is added"""
        initial_count = len(service.request_timestamps)

        await service._wait_for_rate_limit()

        assert len(service.request_timestamps) == initial_count + 1


class TestCreateDocument:
    """Test document creation workflow"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            service = AutentiqueService()
            service.client.execute = Mock()
            return service

    @pytest.mark.asyncio
    async def test_create_document_success(self, service):
        """Test successful document creation"""
        # Mock GraphQL response
        mock_response = {
            "createDocument": {
                "id": "doc_123",
                "name": "Test Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "signatures": [
                    {
                        "public_id": "sig_1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/xyz123"},
                        "user": None,
                        "signed": None,
                        "rejected": None
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        # Mock rate limiting
        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.create_document(
                name="Test Contract",
                file={"base64": "JVBERi0xLjQK"},
                signers=[{"email": "john@example.com", "name": "John Doe"}]
            )

        assert result["id"] == "doc_123"
        assert result["name"] == "Test Contract"
        assert len(result["signatures"]) == 1
        assert result["signatures"][0]["email"] == "john@example.com"

        # Verify GraphQL mutation was called
        service.client.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_document_with_multiple_signers(self, service):
        """Test document creation with multiple signers"""
        mock_response = {
            "createDocument": {
                "id": "doc_456",
                "name": "Multi-Signer Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "signatures": [
                    {
                        "public_id": "sig_1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/xyz123"},
                        "user": None,
                        "signed": None,
                        "rejected": None
                    },
                    {
                        "public_id": "sig_2",
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/abc456"},
                        "user": None,
                        "signed": None,
                        "rejected": None
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.create_document(
                name="Multi-Signer Contract",
                file={"base64": "JVBERi0xLjQK"},
                signers=[
                    {"email": "john@example.com", "name": "John Doe"},
                    {"email": "jane@example.com", "name": "Jane Smith"}
                ]
            )

        assert len(result["signatures"]) == 2
        assert result["signatures"][0]["email"] == "john@example.com"
        assert result["signatures"][1]["email"] == "jane@example.com"

    @pytest.mark.asyncio
    async def test_create_document_with_custom_settings(self, service):
        """Test document creation with custom show_audit_page setting"""
        mock_response = {
            "createDocument": {
                "id": "doc_789",
                "name": "Custom Settings Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "signatures": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            await service.create_document(
                name="Custom Settings Contract",
                file={"base64": "JVBERi0xLjQK"},
                signers=[{"email": "test@example.com", "name": "Test User"}],
                show_audit_page=False
            )

        # Verify the call included show_audit_page parameter
        call_args = service.client.execute.call_args
        document_input = call_args[1]['variable_values']['document']
        assert document_input['show_audit_page'] is False

    @pytest.mark.asyncio
    async def test_create_document_transport_error(self, service):
        """Test handling of GraphQL transport error during document creation"""
        service.client.execute.side_effect = TransportError("Network error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Failed to create document"):
                await service.create_document(
                    name="Test Contract",
                    file={"base64": "JVBERi0xLjQK"},
                    signers=[{"email": "test@example.com", "name": "Test User"}]
                )

    @pytest.mark.asyncio
    async def test_create_document_unexpected_error(self, service):
        """Test handling of unexpected error during document creation"""
        service.client.execute.side_effect = Exception("Unexpected error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Unexpected error"):
                await service.create_document(
                    name="Test Contract",
                    file={"base64": "JVBERi0xLjQK"},
                    signers=[{"email": "test@example.com", "name": "Test User"}]
                )

    @pytest.mark.asyncio
    async def test_create_document_enforces_rate_limit(self, service):
        """Test that create_document enforces rate limiting"""
        mock_response = {"createDocument": {"id": "doc_123", "name": "Test", "signatures": []}}
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit') as mock_rate_limit:
            await service.create_document(
                name="Test Contract",
                file={"base64": "JVBERi0xLjQK"},
                signers=[{"email": "test@example.com", "name": "Test User"}]
            )

            mock_rate_limit.assert_called_once()


class TestGetDocumentStatus:
    """Test document status retrieval"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            service = AutentiqueService()
            service.client.execute = Mock()
            return service

    @pytest.mark.asyncio
    async def test_get_document_status_success(self, service):
        """Test successful document status retrieval"""
        mock_response = {
            "document": {
                "id": "doc_123",
                "name": "Test Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "files": {
                    "original": "https://example.com/original.pdf",
                    "signed": None
                },
                "signatures": [
                    {
                        "public_id": "sig_1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/xyz123"},
                        "signed": None,
                        "rejected": None
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.get_document_status(document_id="doc_123")

        assert result["id"] == "doc_123"
        assert result["name"] == "Test Contract"
        assert len(result["signatures"]) == 1
        assert result["signatures"][0]["signed"] is None

    @pytest.mark.asyncio
    async def test_get_document_status_with_signed_signatures(self, service):
        """Test status retrieval for document with signed signatures"""
        mock_response = {
            "document": {
                "id": "doc_123",
                "name": "Test Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "files": {
                    "original": "https://example.com/original.pdf",
                    "signed": "https://example.com/signed.pdf"
                },
                "signatures": [
                    {
                        "public_id": "sig_1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/xyz123"},
                        "signed": {"created_at": "2026-02-06T11:00:00Z"},
                        "rejected": None
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.get_document_status(document_id="doc_123")

        assert result["signatures"][0]["signed"] is not None
        assert result["signatures"][0]["signed"]["created_at"] == "2026-02-06T11:00:00Z"
        assert result["files"]["signed"] is not None

    @pytest.mark.asyncio
    async def test_get_document_status_with_rejected_signature(self, service):
        """Test status retrieval for document with rejected signature"""
        mock_response = {
            "document": {
                "id": "doc_123",
                "name": "Test Contract",
                "refusable": True,
                "sortable": False,
                "created_at": "2026-02-06T10:00:00Z",
                "files": {
                    "original": "https://example.com/original.pdf",
                    "signed": None
                },
                "signatures": [
                    {
                        "public_id": "sig_1",
                        "name": "John Doe",
                        "email": "john@example.com",
                        "created_at": "2026-02-06T10:00:00Z",
                        "action": "SIGN",
                        "link": {"short_link": "https://autentique.com.br/s/xyz123"},
                        "signed": None,
                        "rejected": {
                            "created_at": "2026-02-06T11:00:00Z",
                            "reason": "Terms not acceptable"
                        }
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.get_document_status(document_id="doc_123")

        assert result["signatures"][0]["rejected"] is not None
        assert result["signatures"][0]["rejected"]["reason"] == "Terms not acceptable"

    @pytest.mark.asyncio
    async def test_get_document_status_transport_error(self, service):
        """Test handling of GraphQL transport error during status check"""
        service.client.execute.side_effect = TransportError("Network error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Failed to get document status"):
                await service.get_document_status(document_id="doc_123")

    @pytest.mark.asyncio
    async def test_get_document_status_unexpected_error(self, service):
        """Test handling of unexpected error during status check"""
        service.client.execute.side_effect = Exception("Unexpected error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Unexpected error"):
                await service.get_document_status(document_id="doc_123")

    @pytest.mark.asyncio
    async def test_get_document_status_enforces_rate_limit(self, service):
        """Test that get_document_status enforces rate limiting"""
        mock_response = {"document": {"id": "doc_123", "name": "Test", "signatures": []}}
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit') as mock_rate_limit:
            await service.get_document_status(document_id="doc_123")

            mock_rate_limit.assert_called_once()


class TestListDocuments:
    """Test document listing with pagination"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            service = AutentiqueService()
            service.client.execute = Mock()
            return service

    @pytest.mark.asyncio
    async def test_list_documents_success(self, service):
        """Test successful document listing"""
        mock_response = {
            "documents": {
                "total": 25,
                "data": [
                    {
                        "id": "doc_1",
                        "name": "Contract 1",
                        "refusable": True,
                        "sortable": False,
                        "created_at": "2026-02-06T10:00:00Z",
                        "signatures": []
                    },
                    {
                        "id": "doc_2",
                        "name": "Contract 2",
                        "refusable": True,
                        "sortable": False,
                        "created_at": "2026-02-05T10:00:00Z",
                        "signatures": []
                    }
                ]
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.list_documents(limit=10, page=1)

        assert result["total"] == 25
        assert len(result["data"]) == 2
        assert result["data"][0]["id"] == "doc_1"
        assert result["data"][1]["id"] == "doc_2"

    @pytest.mark.asyncio
    async def test_list_documents_with_default_pagination(self, service):
        """Test document listing with default pagination parameters"""
        mock_response = {
            "documents": {
                "total": 5,
                "data": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            await service.list_documents()

        # Verify default parameters were used
        call_args = service.client.execute.call_args
        variables = call_args[1]['variable_values']
        assert variables['limit'] == 10
        assert variables['page'] == 1

    @pytest.mark.asyncio
    async def test_list_documents_with_custom_pagination(self, service):
        """Test document listing with custom pagination parameters"""
        mock_response = {
            "documents": {
                "total": 100,
                "data": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            await service.list_documents(limit=50, page=2)

        # Verify custom parameters were used
        call_args = service.client.execute.call_args
        variables = call_args[1]['variable_values']
        assert variables['limit'] == 50
        assert variables['page'] == 2

    @pytest.mark.asyncio
    async def test_list_documents_empty_result(self, service):
        """Test listing when no documents exist"""
        mock_response = {
            "documents": {
                "total": 0,
                "data": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.list_documents()

        assert result["total"] == 0
        assert len(result["data"]) == 0

    @pytest.mark.asyncio
    async def test_list_documents_transport_error(self, service):
        """Test handling of GraphQL transport error during document listing"""
        service.client.execute.side_effect = TransportError("Network error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Failed to list documents"):
                await service.list_documents()

    @pytest.mark.asyncio
    async def test_list_documents_unexpected_error(self, service):
        """Test handling of unexpected error during document listing"""
        service.client.execute.side_effect = Exception("Unexpected error")

        with patch.object(service, '_wait_for_rate_limit'):
            with pytest.raises(AutentiqueAPIError, match="Unexpected error"):
                await service.list_documents()

    @pytest.mark.asyncio
    async def test_list_documents_enforces_rate_limit(self, service):
        """Test that list_documents enforces rate limiting"""
        mock_response = {"documents": {"total": 0, "data": []}}
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit') as mock_rate_limit:
            await service.list_documents()

            mock_rate_limit.assert_called_once()


class TestHelperMethods:
    """Test helper methods for signature checking"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            return AutentiqueService()

    def test_is_document_fully_signed_all_signed(self, service):
        """Test fully signed document returns True"""
        document = {
            "id": "doc_123",
            "signatures": [
                {
                    "email": "john@example.com",
                    "signed": {"created_at": "2026-02-06T10:00:00Z"},
                    "rejected": None
                },
                {
                    "email": "jane@example.com",
                    "signed": {"created_at": "2026-02-06T11:00:00Z"},
                    "rejected": None
                }
            ]
        }

        assert service.is_document_fully_signed(document) is True

    def test_is_document_fully_signed_with_pending(self, service):
        """Test document with pending signatures returns False"""
        document = {
            "id": "doc_123",
            "signatures": [
                {
                    "email": "john@example.com",
                    "signed": {"created_at": "2026-02-06T10:00:00Z"},
                    "rejected": None
                },
                {
                    "email": "jane@example.com",
                    "signed": None,
                    "rejected": None
                }
            ]
        }

        assert service.is_document_fully_signed(document) is False

    def test_is_document_fully_signed_with_rejection(self, service):
        """Test document with rejected signature returns True"""
        document = {
            "id": "doc_123",
            "signatures": [
                {
                    "email": "john@example.com",
                    "signed": {"created_at": "2026-02-06T10:00:00Z"},
                    "rejected": None
                },
                {
                    "email": "jane@example.com",
                    "signed": None,
                    "rejected": {"created_at": "2026-02-06T11:00:00Z", "reason": "Terms not acceptable"}
                }
            ]
        }

        assert service.is_document_fully_signed(document) is True

    def test_is_document_fully_signed_no_signatures_key(self, service):
        """Test document without signatures key returns False"""
        document = {"id": "doc_123"}

        assert service.is_document_fully_signed(document) is False

    def test_is_document_fully_signed_empty_signatures(self, service):
        """Test document with empty signatures list returns True"""
        document = {
            "id": "doc_123",
            "signatures": []
        }

        assert service.is_document_fully_signed(document) is True

    def test_get_pending_signers_with_pending(self, service):
        """Test getting pending signers from document"""
        document = {
            "id": "doc_123",
            "signatures": [
                {
                    "email": "john@example.com",
                    "signed": {"created_at": "2026-02-06T10:00:00Z"},
                    "rejected": None
                },
                {
                    "email": "jane@example.com",
                    "signed": None,
                    "rejected": None
                },
                {
                    "email": "bob@example.com",
                    "signed": None,
                    "rejected": None
                }
            ]
        }

        pending = service.get_pending_signers(document)

        assert len(pending) == 2
        assert "jane@example.com" in pending
        assert "bob@example.com" in pending
        assert "john@example.com" not in pending

    def test_get_pending_signers_all_complete(self, service):
        """Test getting pending signers when all are complete"""
        document = {
            "id": "doc_123",
            "signatures": [
                {
                    "email": "john@example.com",
                    "signed": {"created_at": "2026-02-06T10:00:00Z"},
                    "rejected": None
                },
                {
                    "email": "jane@example.com",
                    "signed": None,
                    "rejected": {"created_at": "2026-02-06T11:00:00Z", "reason": "Not interested"}
                }
            ]
        }

        pending = service.get_pending_signers(document)

        assert len(pending) == 0

    def test_get_pending_signers_no_signatures_key(self, service):
        """Test getting pending signers from document without signatures key"""
        document = {"id": "doc_123"}

        pending = service.get_pending_signers(document)

        assert len(pending) == 0

    def test_get_pending_signers_empty_signatures(self, service):
        """Test getting pending signers from document with empty signatures"""
        document = {
            "id": "doc_123",
            "signatures": []
        }

        pending = service.get_pending_signers(document)

        assert len(pending) == 0


class TestEdgeCases:
    """Test edge cases and unusual scenarios"""

    @pytest.fixture
    def service(self):
        """Create an AutentiqueService instance for testing"""
        with patch('app.services.autentique_service.Client'):
            service = AutentiqueService()
            service.client.execute = Mock()
            return service

    @pytest.mark.asyncio
    async def test_create_document_with_empty_signers_list(self, service):
        """Test document creation with empty signers list"""
        mock_response = {
            "createDocument": {
                "id": "doc_123",
                "name": "Test Contract",
                "signatures": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.create_document(
                name="Test Contract",
                file={"base64": "JVBERi0xLjQK"},
                signers=[]
            )

        assert len(result["signatures"]) == 0

    @pytest.mark.asyncio
    async def test_create_document_with_special_characters_in_name(self, service):
        """Test document creation with special characters in name"""
        mock_response = {
            "createDocument": {
                "id": "doc_123",
                "name": "Contrato José & Filhos - R$ 10.000,00",
                "signatures": []
            }
        }
        service.client.execute.return_value = mock_response

        with patch.object(service, '_wait_for_rate_limit'):
            result = await service.create_document(
                name="Contrato José & Filhos - R$ 10.000,00",
                file={"base64": "JVBERi0xLjQK"},
                signers=[{"email": "jose@example.com", "name": "José Silva"}]
            )

        assert result["name"] == "Contrato José & Filhos - R$ 10.000,00"

    def test_helper_methods_with_missing_signed_rejected_keys(self, service):
        """Test helper methods handle missing signed/rejected keys gracefully"""
        document = {
            "id": "doc_123",
            "signatures": [
                {"email": "john@example.com"}  # Missing signed and rejected keys
            ]
        }

        # Should not raise errors
        assert service.is_document_fully_signed(document) is False
        pending = service.get_pending_signers(document)
        assert "john@example.com" in pending
