"""
Unit tests for Conta Azul API Service

Tests cover:
- Service initialization and configuration
- OAuth 2.0 authorization URL generation
- Token exchange and refresh workflows
- Token expiration checking
- Authenticated API requests
- Customer and contract operations
- Error handling and API failures
- Edge cases and malformed responses
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
import httpx

from app.services.conta_azul_service import (
    ContaAzulService,
    ContaAzulError,
    ContaAzulAuthError,
    ContaAzulAPIError,
    ContaAzulInvalidGrantError,
    _sanitize_error_detail,
)
from app.config import settings


class TestSanitizeErrorDetail:
    """Test redaction of sensitive OAuth information."""

    def test_redacts_json_token_fields(self):
        raw = (
            '{"access_token":"acc-123","refresh_token":"ref-456",'
            '"client_secret":"sec-789","code":"abc-xyz"}'
        )
        sanitized = _sanitize_error_detail(raw)

        assert "[REDACTED]" in sanitized
        assert "acc-123" not in sanitized
        assert "ref-456" not in sanitized
        assert "sec-789" not in sanitized
        assert "abc-xyz" not in sanitized

    def test_redacts_bearer_and_query_tokens(self):
        raw = (
            "Authorization: Bearer tok_12345 "
            "refresh_token=rt_67890 access_token=at_999 code=oauth_code_1"
        )
        sanitized = _sanitize_error_detail(raw)

        assert "[REDACTED]" in sanitized
        assert "tok_12345" not in sanitized
        assert "rt_67890" not in sanitized
        assert "at_999" not in sanitized
        assert "oauth_code_1" not in sanitized

    def test_truncates_very_long_error_detail(self):
        raw = "error=" + ("A" * 1200)
        sanitized = _sanitize_error_detail(raw, max_len=100)

        assert sanitized.endswith("...")
        assert len(sanitized) == 103


class TestContaAzulServiceInitialization:
    """Test Conta Azul service initialization and configuration"""

    def test_initialization_success(self):
        """Test successful service initialization with valid credentials"""
        service = ContaAzulService()

        assert service.client_id == settings.CONTA_AZUL_CLIENT_ID
        assert service.client_secret == settings.CONTA_AZUL_CLIENT_SECRET
        assert service.redirect_uri == settings.CONTA_AZUL_REDIRECT_URI
        assert service.api_base_url == settings.CONTA_AZUL_API_BASE_URL
        # Auth URLs use separate Cognito domain (AUTH_BASE_URL), not api_base_url
        assert service.auth_url == f"{service.AUTH_BASE_URL}{service.AUTH_ENDPOINT}"
        assert service.token_url == f"{service.AUTH_BASE_URL}{service.TOKEN_ENDPOINT}"

    def test_initialization_without_client_id(self):
        """Test that initialization fails without client ID"""
        with patch('app.config.settings.CONTA_AZUL_CLIENT_ID', None):
            with pytest.raises(ValueError, match="Conta Azul API initialization failed"):
                ContaAzulService()

    def test_initialization_without_client_secret(self):
        """Test that initialization fails without client secret"""
        with patch('app.config.settings.CONTA_AZUL_CLIENT_SECRET', None):
            with pytest.raises(ValueError, match="Conta Azul API initialization failed"):
                ContaAzulService()

    def test_initialization_without_redirect_uri(self):
        """Test that initialization fails without redirect URI"""
        with patch('app.config.settings.CONTA_AZUL_REDIRECT_URI', None):
            with pytest.raises(ValueError, match="Conta Azul API initialization failed"):
                ContaAzulService()


class TestGetAuthorizationUrl:
    """Test OAuth authorization URL generation"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    def test_get_authorization_url_default_scope(self, service):
        """Test authorization URL generation with default Cognito scopes"""
        state = "random_state_value"
        auth_url = service.get_authorization_url(state=state)

        # Auth URL uses Cognito domain (AUTH_BASE_URL), not api_base_url
        assert service.AUTH_BASE_URL in auth_url
        assert service.AUTH_ENDPOINT in auth_url
        assert f"client_id={service.client_id}" in auth_url
        assert f"state={state}" in auth_url
        # Default scopes are Cognito scopes, not legacy "sales"
        assert "openid" in auth_url
        assert "profile" in auth_url
        assert "aws.cognito.signin.user.admin" in auth_url

    def test_get_authorization_url_custom_scope(self, service):
        """Test authorization URL generation with custom scopes"""
        state = "random_state_value"
        custom_scopes = ["openid", "profile", "email"]
        auth_url = service.get_authorization_url(state=state, scope=custom_scopes)

        assert service.AUTH_BASE_URL in auth_url
        assert f"state={state}" in auth_url
        assert "openid" in auth_url
        assert "profile" in auth_url
        assert "email" in auth_url

    def test_get_authorization_url_single_custom_scope(self, service):
        """Test authorization URL generation with single custom scope"""
        state = "test_state"
        custom_scopes = ["customer"]
        auth_url = service.get_authorization_url(state=state, scope=custom_scopes)

        assert "scope=customer" in auth_url
        assert f"state={state}" in auth_url


class TestExchangeCodeForToken:
    """Test authorization code exchange for tokens"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, service):
        """Test successful token exchange"""
        mock_token_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            result = await service.exchange_code_for_token(code="test_auth_code")

            assert result["access_token"] == "test_access_token"
            assert result["refresh_token"] == "test_refresh_token"
            assert result["expires_in"] == 3600
            assert result["token_type"] == "Bearer"
            assert "expires_at" in result

            # Verify expires_at is a valid ISO format timestamp
            expires_at = datetime.fromisoformat(result["expires_at"])
            assert isinstance(expires_at, datetime)

    @pytest.mark.asyncio
    async def test_exchange_code_with_custom_expires_in(self, service):
        """Test token exchange with custom expiration time"""
        mock_token_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 7200,
            "token_type": "Bearer"
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            result = await service.exchange_code_for_token(code="test_auth_code")

            assert result["expires_in"] == 7200

    @pytest.mark.asyncio
    async def test_exchange_code_failure_invalid_code(self, service):
        """Test token exchange failure with invalid authorization code"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid authorization code"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAuthError, match="Failed to exchange authorization code"):
                await service.exchange_code_for_token(code="invalid_code")

    @pytest.mark.asyncio
    async def test_exchange_code_failure_unauthorized(self, service):
        """Test token exchange failure with unauthorized client"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized client"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAuthError, match="Failed to exchange authorization code"):
                await service.exchange_code_for_token(code="test_code")

    @pytest.mark.asyncio
    async def test_exchange_code_network_error(self, service):
        """Test token exchange with network error"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.RequestError("Network error")
            )

            with pytest.raises(ContaAzulAuthError, match="Network error during authentication"):
                await service.exchange_code_for_token(code="test_code")

    @pytest.mark.asyncio
    async def test_exchange_code_unexpected_error(self, service):
        """Test token exchange with unexpected error"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Unexpected error")
            )

            with pytest.raises(ContaAzulAuthError, match="Unexpected authentication error"):
                await service.exchange_code_for_token(code="test_code")


class TestRefreshAccessToken:
    """Test access token refresh workflow"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, service):
        """Test successful token refresh"""
        mock_token_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            result = await service.refresh_access_token(refresh_token="old_refresh_token")

            assert result["access_token"] == "new_access_token"
            assert result["refresh_token"] == "new_refresh_token"
            assert result["expires_in"] == 3600
            assert "expires_at" in result

    @pytest.mark.asyncio
    async def test_refresh_token_failure_invalid_token(self, service):
        """Test token refresh failure with invalid refresh token"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid refresh token"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAuthError, match="Failed to refresh access token"):
                await service.refresh_access_token(refresh_token="invalid_token")

    @pytest.mark.asyncio
    async def test_refresh_token_network_error(self, service):
        """Test token refresh with network error"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.RequestError("Connection timeout")
            )

            with pytest.raises(ContaAzulAuthError, match="Network error during token refresh"):
                await service.refresh_access_token(refresh_token="test_token")

    @pytest.mark.asyncio
    async def test_refresh_token_unexpected_error(self, service):
        """Test token refresh with unexpected error"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Unexpected error")
            )

            with pytest.raises(ContaAzulAuthError, match="Unexpected token refresh error"):
                await service.refresh_access_token(refresh_token="test_token")

    @pytest.mark.asyncio
    async def test_refresh_token_invalid_grant_error(self, service):
        """Test that invalid_grant response raises ContaAzulInvalidGrantError.

        When the refresh_token is revoked, expired, or otherwise permanently
        invalid, Cognito returns an error containing 'invalid_grant'.
        The service must raise ContaAzulInvalidGrantError so callers know
        a full re-authorization is needed.
        """
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "invalid_grant", "error_description": "Refresh Token has been revoked"}'

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulInvalidGrantError, match="Refresh token inválido"):
                await service.refresh_access_token(refresh_token="revoked_token")

    @pytest.mark.asyncio
    async def test_refresh_token_invalid_grant_is_subclass_of_auth_error(self, service):
        """Test that ContaAzulInvalidGrantError is catchable as ContaAzulAuthError"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant: token has expired"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Should also be catchable as ContaAzulAuthError (parent class)
            with pytest.raises(ContaAzulAuthError):
                await service.refresh_access_token(refresh_token="expired_token")


class TestIsTokenExpired:
    """Test token expiration checking"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    def test_token_not_expired(self, service):
        """Test that valid token is not marked as expired"""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        assert service.is_token_expired(expires_at) is False

    def test_token_expired(self, service):
        """Test that expired token is marked as expired"""
        expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        assert service.is_token_expired(expires_at) is True

    def test_token_expires_soon(self, service):
        """Test that token expiring within 60 seconds is marked as expired"""
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()

        assert service.is_token_expired(expires_at) is True

    def test_token_expires_just_after_buffer(self, service):
        """Test that token expiring just after 60-second buffer is not expired"""
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()

        assert service.is_token_expired(expires_at) is False

    def test_invalid_expires_at_format(self, service):
        """Test that invalid timestamp format is treated as expired"""
        assert service.is_token_expired("invalid_timestamp") is True
        assert service.is_token_expired("2026-13-45 25:99:99") is True
        assert service.is_token_expired("") is True

    def test_none_expires_at(self, service):
        """Test that None value is treated as expired"""
        assert service.is_token_expired(None) is True


class TestMakeApiRequest:
    """Test authenticated API request making"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_make_api_request_get_success(self, service):
        """Test successful GET API request"""
        mock_response_data = {"data": [{"id": 1, "name": "Customer 1"}]}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            result = await service.make_api_request(
                endpoint="/v1/customers",
                access_token="test_token",
                method="GET"
            )

            assert result == mock_response_data

    @pytest.mark.asyncio
    async def test_make_api_request_post_success(self, service):
        """Test successful POST API request"""
        mock_response_data = {"id": 1, "name": "New Customer"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            result = await service.make_api_request(
                endpoint="/v1/customers",
                access_token="test_token",
                method="POST",
                json_data={"name": "New Customer"}
            )

            assert result == mock_response_data

    @pytest.mark.asyncio
    async def test_make_api_request_with_params(self, service):
        """Test API request with query parameters"""
        mock_response_data = {"data": []}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch('httpx.AsyncClient') as mock_client:
            mock_request = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.request = mock_request

            await service.make_api_request(
                endpoint="/v1/customers",
                access_token="test_token",
                method="GET",
                params={"search": "João", "size": 50}
            )

            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args[1]
            assert call_kwargs["params"] == {"search": "João", "size": 50}

    @pytest.mark.asyncio
    async def test_make_api_request_204_no_content(self, service):
        """Test API request with 204 No Content response"""
        mock_response = Mock()
        mock_response.status_code = 204

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            result = await service.make_api_request(
                endpoint="/v1/customers/1",
                access_token="test_token",
                method="DELETE"
            )

            assert result == {}

    @pytest.mark.asyncio
    async def test_make_api_request_401_unauthorized(self, service):
        """Test API request with 401 unauthorized (expired token)"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAuthError, match="Access token is invalid or expired"):
                await service.make_api_request(
                    endpoint="/v1/customers",
                    access_token="expired_token",
                    method="GET"
                )

    @pytest.mark.asyncio
    async def test_make_api_request_400_bad_request(self, service):
        """Test API request with 400 bad request"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request parameters"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAPIError, match="API request failed: 400"):
                await service.make_api_request(
                    endpoint="/v1/customers",
                    access_token="test_token",
                    method="POST",
                    json_data={"invalid": "data"}
                )

    @pytest.mark.asyncio
    async def test_make_api_request_404_not_found(self, service):
        """Test API request with 404 not found"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Resource not found"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAPIError, match="API request failed: 404"):
                await service.make_api_request(
                    endpoint="/v1/customers/999",
                    access_token="test_token",
                    method="GET"
                )

    @pytest.mark.asyncio
    async def test_make_api_request_500_server_error(self, service):
        """Test API request with 500 server error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)

            with pytest.raises(ContaAzulAPIError, match="API request failed: 500"):
                await service.make_api_request(
                    endpoint="/v1/customers",
                    access_token="test_token",
                    method="GET"
                )

    @pytest.mark.asyncio
    async def test_make_api_request_network_error(self, service):
        """Test API request with network error"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )

            with pytest.raises(ContaAzulAPIError, match="Network error"):
                await service.make_api_request(
                    endpoint="/v1/customers",
                    access_token="test_token",
                    method="GET"
                )

    @pytest.mark.asyncio
    async def test_make_api_request_timeout(self, service):
        """Test API request with timeout"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )

            with pytest.raises(ContaAzulAPIError, match="Network error"):
                await service.make_api_request(
                    endpoint="/v1/customers",
                    access_token="test_token",
                    method="GET"
                )


class TestGetCustomers:
    """Test customer (pessoa) retrieval operations via /v1/pessoas endpoint"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_customers_success(self, service):
        """Test successful pessoa retrieval with pagination"""
        mock_customers = [
            {"id": 1, "name": "Customer 1"},
            {"id": 2, "name": "Customer 2"}
        ]

        # get_customers uses internal pagination loop; first call returns data,
        # second call returns empty list to stop pagination
        with patch.object(service, 'make_api_request', new=AsyncMock(
            side_effect=[mock_customers, []]
        )):
            result = await service.get_customers(access_token="test_token")

            assert result == mock_customers
            # First call should use /v1/pessoas with pagina/tamanho_pagina
            first_call = service.make_api_request.call_args_list[0]
            assert first_call[1]["endpoint"] == "/v1/pessoas"
            assert first_call[1]["params"]["pagina"] == 1
            assert first_call[1]["params"]["tamanho_pagina"] == 100

    @pytest.mark.asyncio
    async def test_get_customers_with_search(self, service):
        """Test pessoa retrieval with busca (search) parameter"""
        mock_customers = [{"id": 1, "name": "João Silva"}]

        with patch.object(service, 'make_api_request', new=AsyncMock(
            side_effect=[mock_customers, []]
        )):
            result = await service.get_customers(
                access_token="test_token",
                search="João"
            )

            assert result == mock_customers
            first_call = service.make_api_request.call_args_list[0]
            assert first_call[1]["params"]["busca"] == "João"

    @pytest.mark.asyncio
    async def test_get_customers_with_custom_limit(self, service):
        """Test pessoa retrieval with custom tamanho_pagina limit"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=[])):
            await service.get_customers(
                access_token="test_token",
                limit=50
            )

            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["tamanho_pagina"] == 50

    @pytest.mark.asyncio
    async def test_get_customers_empty_result(self, service):
        """Test pessoa retrieval with empty result (stops pagination)"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=[])):
            result = await service.get_customers(access_token="test_token")

            assert result == []

    @pytest.mark.asyncio
    async def test_get_customers_pagination_multiple_pages(self, service):
        """Test pessoa retrieval with multiple pages of results"""
        page1 = [{"id": i, "name": f"Customer {i}"} for i in range(100)]
        page2 = [{"id": 101, "name": "Customer 101"}]

        # Use limit=150 so the service does NOT stop after page 1
        # (default limit=100 would satisfy len(all) >= limit after first page)
        with patch.object(service, 'make_api_request', new=AsyncMock(
            side_effect=[page1, page2, []]
        )):
            result = await service.get_customers(
                access_token="test_token",
                limit=150
            )

            # page1 (100) + page2 (1) = 101 total, all under limit 150
            assert len(result) == 101
            # Should have called page 1, page 2, and page 3 (empty → stops)
            assert service.make_api_request.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_customers_response_with_data_field(self, service):
        """Test pessoa retrieval when response wraps results in data field"""
        mock_customers = [{"id": 1, "name": "Customer 1"}]

        with patch.object(service, 'make_api_request', new=AsyncMock(
            side_effect=[{"data": mock_customers}, []]
        )):
            result = await service.get_customers(access_token="test_token")

            assert result == mock_customers


class TestCreateCustomer:
    """Test customer creation operations"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_create_customer_success(self, service):
        """Test successful customer creation"""
        customer_data = {
            "name": "João Silva",
            "document": "12345678900",
            "email": "joao@example.com"
        }

        mock_response = {
            "id": 123,
            **customer_data
        }

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_response)):
            result = await service.create_customer(
                access_token="test_token",
                customer_data=customer_data
            )

            assert result["id"] == 123
            assert result["name"] == customer_data["name"]
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/pessoas",
                access_token="test_token",
                method="POST",
                json_data=customer_data
            )

    @pytest.mark.asyncio
    async def test_create_customer_with_minimal_data(self, service):
        """Test customer creation with minimal required data"""
        customer_data = {"name": "Minimal Customer"}
        mock_response = {"id": 456, "name": "Minimal Customer"}

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_response)):
            result = await service.create_customer(
                access_token="test_token",
                customer_data=customer_data
            )

            assert result["id"] == 456


class TestGetContracts:
    """Test contract retrieval operations"""

    @pytest.fixture
    def service(self):
        """Create a ContaAzulService instance for testing"""
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_contracts_success(self, service):
        """Test successful contract retrieval"""
        mock_contracts = [
            {"id": 1, "status": "ACTIVE"},
            {"id": 2, "status": "PENDING"}
        ]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value={"data": mock_contracts})):
            result = await service.get_contracts(access_token="test_token")

            assert result == mock_contracts
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/contracts",
                access_token="test_token",
                method="GET",
                params={"size": 100}
            )

    @pytest.mark.asyncio
    async def test_get_contracts_with_status_filter(self, service):
        """Test contract retrieval with status filter"""
        mock_contracts = [{"id": 1, "status": "ACTIVE"}]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value={"data": mock_contracts})):
            result = await service.get_contracts(
                access_token="test_token",
                status="ACTIVE"
            )

            assert result == mock_contracts
            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_contracts_with_custom_limit(self, service):
        """Test contract retrieval with custom limit"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value={"data": []})):
            await service.get_contracts(
                access_token="test_token",
                limit=25
            )

            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["size"] == 25

    @pytest.mark.asyncio
    async def test_get_contracts_empty_result(self, service):
        """Test contract retrieval with empty result"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value={"data": []})):
            result = await service.get_contracts(access_token="test_token")

            assert result == []

    @pytest.mark.asyncio
    async def test_get_contracts_no_data_field(self, service):
        """Test contract retrieval when response has no data field"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value={})):
            result = await service.get_contracts(access_token="test_token")

            assert result == []


class TestGetContasReceber:
    """Test accounts receivable (contas a receber) retrieval"""

    @pytest.fixture
    def service(self):
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_contas_receber_success(self, service):
        """Test successful retrieval of contas a receber"""
        mock_data = [
            {"id": 1, "valor": 1500.00, "status": "PENDENTE"},
            {"id": 2, "valor": 3000.00, "status": "PAGO"}
        ]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_data)):
            result = await service.get_contas_receber(access_token="test_token")

            assert result == mock_data
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
                access_token="test_token",
                method="GET",
                params={"pagina": 1, "tamanho_pagina": 100}
            )

    @pytest.mark.asyncio
    async def test_get_contas_receber_with_filters(self, service):
        """Test contas a receber with status and date filters"""
        mock_data = [{"id": 1, "valor": 1500.00, "status": "PENDENTE"}]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_data)):
            result = await service.get_contas_receber(
                access_token="test_token",
                status_filter="PENDENTE",
                data_vencimento_inicio="2026-01-01",
                data_vencimento_fim="2026-12-31"
            )

            assert result == mock_data
            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["status"] == "PENDENTE"
            assert call_kwargs["params"]["data_vencimento_de"] == "2026-01-01"
            assert call_kwargs["params"]["data_vencimento_ate"] == "2026-12-31"

    @pytest.mark.asyncio
    async def test_get_contas_receber_empty(self, service):
        """Test contas a receber with empty result"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=[])):
            result = await service.get_contas_receber(access_token="test_token")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_contas_receber_dict_response(self, service):
        """Test contas a receber when API returns dict with data field"""
        mock_items = [{"id": 1, "valor": 500.00}]
        with patch.object(service, 'make_api_request', new=AsyncMock(
            return_value={"data": mock_items}
        )):
            result = await service.get_contas_receber(access_token="test_token")
            assert result == mock_items

    @pytest.mark.asyncio
    async def test_get_contas_receber_with_ids_clientes_filter(self, service):
        """Test contas a receber with ids_clientes filter."""
        with patch.object(service, "make_api_request", new=AsyncMock(return_value=[])):
            await service.get_contas_receber(
                access_token="test_token",
                ids_clientes=["cli-1", " ", "cli-2"],
            )

            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["ids_clientes"] == ["cli-1", "cli-2"]


class TestGetContasPagar:
    """Test accounts payable (contas a pagar) retrieval"""

    @pytest.fixture
    def service(self):
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_contas_pagar_success(self, service):
        """Test successful retrieval of contas a pagar"""
        mock_data = [
            {"id": 1, "valor": 800.00, "status": "PENDENTE"},
            {"id": 2, "valor": 1200.00, "status": "PAGO"}
        ]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_data)):
            result = await service.get_contas_pagar(access_token="test_token")

            assert result == mock_data
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
                access_token="test_token",
                method="GET",
                params={"pagina": 1, "tamanho_pagina": 100}
            )

    @pytest.mark.asyncio
    async def test_get_contas_pagar_with_filters(self, service):
        """Test contas a pagar with status and date filters"""
        mock_data = [{"id": 1, "valor": 800.00}]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_data)):
            result = await service.get_contas_pagar(
                access_token="test_token",
                status_filter="PENDENTE",
                data_vencimento_inicio="2026-03-01",
                data_vencimento_fim="2026-03-31"
            )

            assert result == mock_data
            call_kwargs = service.make_api_request.call_args[1]
            assert call_kwargs["params"]["status"] == "PENDENTE"
            assert call_kwargs["params"]["data_vencimento_de"] == "2026-03-01"
            assert call_kwargs["params"]["data_vencimento_ate"] == "2026-03-31"

    @pytest.mark.asyncio
    async def test_get_contas_pagar_empty(self, service):
        """Test contas a pagar with empty result"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=[])):
            result = await service.get_contas_pagar(access_token="test_token")
            assert result == []


class TestGetContasFinanceiras:
    """Test financial accounts (contas financeiras) retrieval"""

    @pytest.fixture
    def service(self):
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_contas_financeiras_success(self, service):
        """Test successful retrieval of contas financeiras"""
        mock_data = [
            {"id": "acc-1", "nome": "Conta Corrente BB", "saldo": 15000.00},
            {"id": "acc-2", "nome": "Conta Poupança", "saldo": 50000.00}
        ]

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_data)):
            result = await service.get_contas_financeiras(access_token="test_token")

            assert result == mock_data
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/conta-financeira",
                access_token="test_token",
                method="GET"
            )

    @pytest.mark.asyncio
    async def test_get_contas_financeiras_empty(self, service):
        """Test contas financeiras with empty result"""
        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=[])):
            result = await service.get_contas_financeiras(access_token="test_token")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_contas_financeiras_dict_response(self, service):
        """Test contas financeiras when API returns dict with content field"""
        mock_items = [{"id": "acc-1", "nome": "Conta"}]
        with patch.object(service, 'make_api_request', new=AsyncMock(
            return_value={"content": mock_items}
        )):
            result = await service.get_contas_financeiras(access_token="test_token")
            assert result == mock_items


class TestGetSaldoConta:
    """Test individual financial account balance retrieval"""

    @pytest.fixture
    def service(self):
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_saldo_conta_success(self, service):
        """Test successful balance retrieval for a specific account"""
        mock_saldo = {"saldo_atual": 15000.00, "data_consulta": "2026-02-13"}

        with patch.object(service, 'make_api_request', new=AsyncMock(return_value=mock_saldo)):
            result = await service.get_saldo_conta(
                access_token="test_token",
                conta_id="acc-123"
            )

            assert result == mock_saldo
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/conta-financeira/acc-123/saldo-atual",
                access_token="test_token",
                method="GET"
            )

    @pytest.mark.asyncio
    async def test_get_saldo_conta_not_found(self, service):
        """Test balance retrieval for non-existent account"""
        with patch.object(service, 'make_api_request', new=AsyncMock(
            side_effect=ContaAzulAPIError("API request failed: 404 - Resource not found")
        )):
            with pytest.raises(ContaAzulAPIError, match="404"):
                await service.get_saldo_conta(
                    access_token="test_token",
                    conta_id="non-existent"
                )


class TestSalesAndProductUpdates:
    """Tests for Conta Azul changelog integrations (sales items/product image/payment enum)."""

    @pytest.fixture
    def service(self):
        return ContaAzulService()

    @pytest.mark.asyncio
    async def test_get_venda_itens_by_sale_id_success(self, service):
        """Must accept only allowed page sizes and expose id_centro_custo."""
        mock_items = [{"id": "i-1", "descricao": "Item A", "id_centro_custo": "cc-1"}, {"id": "i-2", "descricao": "Item B"}]

        with patch.object(service, "make_api_request", new=AsyncMock(return_value={"itens": mock_items})):
            result = await service.get_venda_itens_by_sale_id(
                access_token="test_token",
                sale_id="sale-123",
                pagina=2,
                tamanho_pagina=200,
            )

            assert len(result) == 2
            assert result[0]["id_centro_custo"] == "cc-1"
            assert result[1]["id_centro_custo"] is None
            service.make_api_request.assert_called_once_with(
                endpoint="/v1/vendas/sale-123/itens",
                access_token="test_token",
                method="GET",
                params={"pagina": 2, "tamanho_pagina": 200},
            )

    @pytest.mark.asyncio
    async def test_get_venda_itens_by_sale_id_rejects_invalid_page_size(self, service):
        with pytest.raises(ValueError, match="tamanho_pagina must be one of"):
            await service.get_venda_itens_by_sale_id(
                access_token="test_token",
                sale_id="sale-123",
                tamanho_pagina=30,
            )

    @pytest.mark.asyncio
    async def test_get_produto_by_id_keeps_url_imagem(self, service):
        with patch.object(service, "make_api_request", new=AsyncMock(return_value={"id": "p-1", "nome": "Produto"})):
            result = await service.get_produto_by_id(
                access_token="test_token",
                product_id="p-1",
            )

            assert result["id"] == "p-1"
            assert "url_imagem" in result
            assert result["url_imagem"] is None

    def test_normalize_payment_type_maps_legacy_pix_enum(self, service):
        assert service.normalize_payment_type("PAGAMENTO_INSTANTANEO") == "PIX_PAGAMENTO_INSTANTANEO"
        assert service.normalize_payment_type("pix") == "PIX_PAGAMENTO_INSTANTANEO"
        assert service.normalize_payment_type("PIX_PAGAMENTO_INSTANTANEO") == "PIX_PAGAMENTO_INSTANTANEO"
