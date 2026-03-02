"""
Conta Azul API Service Client

This module provides a service client for interacting with Conta Azul's API
for accounting platform integration using OAuth 2.0 authentication.

The service handles:
- OAuth 2.0 Authorization Code flow
- Access token and refresh token management
- Automatic token refresh on expiration
- Authenticated API requests to Conta Azul resources
- Rate limiting and error handling

Conta Azul API supports operations for:
- Customer management
- Product and service catalog
- Contract management
- Sales and invoicing

Usage:
    from app.services.conta_azul_service import ContaAzulService

    service = ContaAzulService()

    # Get authorization URL for user consent
    auth_url = service.get_authorization_url(state="random_state")

    # Exchange authorization code for tokens
    tokens = await service.exchange_code_for_token(code="auth_code")

    # Make authenticated API calls
    customers = await service.get_customers(access_token=tokens["access_token"])

    # Refresh expired tokens
    new_tokens = await service.refresh_access_token(refresh_token=tokens["refresh_token"])

References:
    - https://developers.contaazul.com/auth
    - OAuth 2.0 Authorization Code flow
"""

import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import urlencode
import re

from app.config import settings

logger = logging.getLogger(__name__)


def _sanitize_error_detail(raw_detail: Any, max_len: int = 300) -> str:
    """
    Redact sensitive OAuth material before logging/raising provider errors.

    Masks token-like values and credential fields while keeping enough context
    (status/code/message) for troubleshooting.
    """
    text = str(raw_detail or "").strip()
    if not text:
        return ""

    text = re.sub(
        r'("?(?:access_token|refresh_token|client_secret|authorization_code|code)"?\s*[:=]\s*"?)([^",\s]+)("?)',
        lambda m: f"{m.group(1)}[REDACTED]{m.group(3) or ''}",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(Bearer\s+)([A-Za-z0-9._\-]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(client_secret=)([^&\s]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(refresh_token=)([^&\s]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(access_token=)([^&\s]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(code=)([^&\s]+)", r"\1[REDACTED]", text, flags=re.IGNORECASE)

    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


class ContaAzulError(Exception):
    """Base exception for Conta Azul API errors."""
    pass


class ContaAzulAuthError(ContaAzulError):
    """Exception raised for authentication/authorization errors."""
    pass


class ContaAzulInvalidGrantError(ContaAzulAuthError):
    """Exception raised when refresh_token is invalid, expired, or revoked.

    This error specifically indicates that a full OAuth re-authorization is
    required — the user must go through the consent flow again.
    """
    pass


class ContaAzulAPIError(ContaAzulError):
    """Exception raised for API request errors."""
    pass


class ContaAzulService:
    """
    Service client for Conta Azul API integration with OAuth 2.0 (AWS Cognito).

    Provides methods for OAuth 2.0 authentication flow and authenticated
    API requests to Conta Azul's accounting platform.

    The client uses credentials from environment variables:
    - CONTA_AZUL_CLIENT_ID: Application client ID
    - CONTA_AZUL_CLIENT_SECRET: Application client secret
    - CONTA_AZUL_REDIRECT_URI: OAuth callback URL
    - CONTA_AZUL_API_BASE_URL: API base URL (default: https://api-v2.contaazul.com)

    Attributes:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        redirect_uri: OAuth redirect URI
        api_base_url: API base URL for data requests
        auth_url: Authorization endpoint URL (Cognito)
        token_url: Token endpoint URL (Cognito)
    """

    # OAuth 2.0 endpoints (AWS Cognito - migrated from legacy api.contaazul.com)
    AUTH_BASE_URL = "https://auth.contaazul.com"
    AUTH_ENDPOINT = "/oauth2/authorize"
    TOKEN_ENDPOINT = "/oauth2/token"

    # Token expiration (60 minutes as per Conta Azul documentation)
    TOKEN_LIFETIME_SECONDS = 3600

    # OAuth scopes for AWS Cognito (replaces legacy "sales" scope)
    SCOPES = ["openid", "profile", "aws.cognito.signin.user.admin"]
    SALES_ITEMS_ALLOWED_PAGE_SIZES = {10, 20, 50, 100, 200, 500, 1000}
    LEGACY_PIX_PAYMENT_TYPE = "PAGAMENTO_INSTANTANEO"
    CANONICAL_PIX_PAYMENT_TYPE = "PIX_PAGAMENTO_INSTANTANEO"

    def __init__(self):
        """
        Initialize Conta Azul API client with OAuth credentials.

        Reads configuration from settings (environment variables).
        Raises ValueError if required credentials are not configured.
        """
        self.client_id = getattr(settings, "CONTA_AZUL_CLIENT_ID", None)
        self.client_secret = getattr(settings, "CONTA_AZUL_CLIENT_SECRET", None)
        self.redirect_uri = getattr(settings, "CONTA_AZUL_REDIRECT_URI", None)
        self.api_base_url = getattr(settings, "CONTA_AZUL_API_BASE_URL", None)

        # Validate — pydantic-settings may provide empty strings instead of
        # raising AttributeError, so we must check explicitly.
        missing = [
            name for name, val in [
                ("CONTA_AZUL_CLIENT_ID", self.client_id),
                ("CONTA_AZUL_CLIENT_SECRET", self.client_secret),
                ("CONTA_AZUL_REDIRECT_URI", self.redirect_uri),
            ] if not val
        ]
        if missing:
            msg = (
                f"Conta Azul API initialization failed. "
                f"Missing required configuration: {', '.join(missing)}"
            )
            logger.error(msg)
            raise ValueError(msg)

        # Auth endpoints on Cognito domain (auth.contaazul.com)
        self.auth_url = f"{self.AUTH_BASE_URL}{self.AUTH_ENDPOINT}"
        self.token_url = f"{self.AUTH_BASE_URL}{self.TOKEN_ENDPOINT}"

        logger.info(f"Conta Azul service initialized - Auth: {self.AUTH_BASE_URL}, API: {self.api_base_url}")

    def get_authorization_url(
        self,
        state: str,
        scope: Optional[List[str]] = None
    ) -> str:
        """
        Generate OAuth 2.0 authorization URL for user consent.

        This URL should be used to redirect the user to Conta Azul's
        authorization page where they grant access to their account.

        Args:
            state: Random state value for CSRF protection (should be verified
                  when handling the callback)
            scope: List of permission scopes to request. Defaults to ["sales"].
                  Available scopes: sales, customer, product, service, contract

        Returns:
            Complete authorization URL to redirect user to

        Example:
            >>> service = ContaAzulService()
            >>> auth_url = service.get_authorization_url(state="random_uuid_here")
            >>> # Redirect user to auth_url
            >>> # User grants access and is redirected back with code parameter
        """
        scopes = scope or self.SCOPES
        scope_string = " ".join(scopes)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope_string,
            "state": state
        }

        authorization_url = f"{self.auth_url}?{urlencode(params)}"

        logger.info(f"Generated authorization URL with scopes: {scope_string}")
        return authorization_url

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        After user grants consent, Conta Azul redirects back with an
        authorization code. This method exchanges that code for tokens.

        Args:
            code: Authorization code received from OAuth callback

        Returns:
            Dictionary containing:
                - access_token: Bearer token for API requests
                - refresh_token: Token for obtaining new access tokens
                - expires_in: Token lifetime in seconds (3600 = 60 minutes)
                - token_type: Token type (always "Bearer")
                - expires_at: Calculated expiration timestamp (ISO format)

        Raises:
            ContaAzulAuthError: If token exchange fails

        Example:
            >>> service = ContaAzulService()
            >>> tokens = await service.exchange_code_for_token(code="auth_code_123")
            >>> access_token = tokens["access_token"]
            >>> # Store tokens securely for later use
        """
        # AWS Cognito token exchange - send credentials in body only
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info("Exchanging authorization code for tokens")

                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                logger.info(f"Token exchange response status: {response.status_code}")

                if response.status_code != 200:
                    error_detail = _sanitize_error_detail(response.text)
                    logger.error("Token exchange failed with status %s", response.status_code)
                    raise ContaAzulAuthError(
                        f"Failed to exchange authorization code: {response.status_code} - {error_detail}"
                    )

                token_data = response.json()

                # Calculate token expiration timestamp
                expires_in = token_data.get("expires_in", self.TOKEN_LIFETIME_SECONDS)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                token_data["expires_at"] = expires_at.isoformat()

                logger.info("Successfully obtained access token")
                return token_data

        except httpx.RequestError as e:
            logger.error(f"Network error during token exchange: {e}")
            raise ContaAzulAuthError(f"Network error during authentication: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            raise ContaAzulAuthError(f"Unexpected authentication error: {e}")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token using a refresh token.

        Access tokens expire after 60 minutes. Use this method to obtain
        a new access token without requiring user consent again.

        Args:
            refresh_token: Valid refresh token from previous authentication

        Returns:
            Dictionary containing new tokens (same structure as exchange_code_for_token)
                - access_token: New bearer token for API requests
                - refresh_token: New refresh token (old one is invalidated)
                - expires_in: Token lifetime in seconds
                - token_type: Token type (always "Bearer")
                - expires_at: Calculated expiration timestamp (ISO format)

        Raises:
            ContaAzulAuthError: If token refresh fails

        Example:
            >>> service = ContaAzulService()
            >>> new_tokens = await service.refresh_access_token(
            ...     refresh_token="stored_refresh_token"
            ... )
            >>> # Update stored tokens with new values
        """
        # Send credentials in body ONLY — do NOT also use basic auth header,
        # as Cognito may reject the request when credentials appear in both places.
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Refreshing access token at {self.token_url}")

                response = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code != 200:
                    raw_error_detail = response.text
                    error_detail = _sanitize_error_detail(raw_error_detail)
                    logger.error("Token refresh failed with status %s", response.status_code)

                    # Detect invalid_grant specifically — means refresh_token is
                    # revoked, expired, or otherwise permanently invalid.
                    # A full OAuth re-authorization is the only recovery path.
                    if "invalid_grant" in raw_error_detail.lower():
                        logger.error(
                            "INVALID_GRANT detected — refresh_token is permanently "
                            "invalid. Full OAuth re-authorization required."
                        )
                        raise ContaAzulInvalidGrantError(
                            "Refresh token inválido/expirado/revogado. "
                            "É necessário reautorizar a integração com o Conta Azul "
                            "via GET /api/auth/conta-azul/authorize"
                        )

                    raise ContaAzulAuthError(
                        f"Failed to refresh access token: {response.status_code} - {error_detail}"
                    )

                token_data = response.json()

                # Calculate token expiration timestamp
                expires_in = token_data.get("expires_in", self.TOKEN_LIFETIME_SECONDS)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                token_data["expires_at"] = expires_at.isoformat()

                logger.info("Successfully refreshed access token")
                return token_data

        except (ContaAzulInvalidGrantError, ContaAzulAuthError):
            raise  # Re-raise auth errors without wrapping
        except httpx.RequestError as e:
            logger.error(f"Network error during token refresh: {e}")
            raise ContaAzulAuthError(f"Network error during token refresh: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            raise ContaAzulAuthError(f"Unexpected token refresh error: {e}")

    def is_token_expired(self, expires_at: str) -> bool:
        """
        Check if an access token has expired.

        Args:
            expires_at: ISO format timestamp from token response

        Returns:
            True if token is expired or will expire within 60 seconds,
            False if token is still valid

        Example:
            >>> service = ContaAzulService()
            >>> if service.is_token_expired(tokens["expires_at"]):
            ...     tokens = await service.refresh_access_token(tokens["refresh_token"])
        """
        try:
            expiration = datetime.fromisoformat(expires_at)
            # Ensure timezone-aware comparison: if the stored timestamp is
            # naive (no tzinfo), assume UTC to avoid TypeError on Python 3.12+
            if expiration.tzinfo is None:
                expiration = expiration.replace(tzinfo=timezone.utc)
            # Add 60 second buffer to avoid race conditions
            return datetime.now(timezone.utc) >= (expiration - timedelta(seconds=60))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid expires_at format: {e}")
            return True  # Assume expired if format is invalid

    async def make_api_request(
        self,
        endpoint: str,
        access_token: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request to Conta Azul.

        Handles all HTTP methods and automatically includes authentication
        headers with the access token.

        Args:
            endpoint: API endpoint path (e.g., "/v1/customers")
            access_token: Valid OAuth access token
            method: HTTP method (GET, POST, PUT, DELETE)
            params: Query parameters for GET requests
            json_data: JSON body for POST/PUT requests

        Returns:
            API response as dictionary

        Raises:
            ContaAzulAPIError: If API request fails

        Example:
            >>> service = ContaAzulService()
            >>> customers = await service.make_api_request(
            ...     endpoint="/v1/customers",
            ...     access_token=tokens["access_token"],
            ...     method="GET"
            ... )
        """
        url = f"{self.api_base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Making {method} request to {endpoint}")

                response = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    timeout=30.0
                )

                if response.status_code == 401:
                    logger.error("Access token is invalid or expired")
                    raise ContaAzulAuthError("Access token is invalid or expired. Please refresh token.")

                if response.status_code >= 400:
                    error_detail = _sanitize_error_detail(response.text)
                    logger.error("API request failed with status %s on %s", response.status_code, endpoint)
                    raise ContaAzulAPIError(
                        f"API request failed: {response.status_code} - {error_detail}"
                    )

                # Handle 204 No Content responses
                if response.status_code == 204:
                    return {}

                return response.json()

        except httpx.RequestError as e:
            logger.error(f"Network error during API request: {e}")
            raise ContaAzulAPIError(f"Network error: {e}")
        except ContaAzulAuthError:
            raise  # Re-raise auth errors
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            raise ContaAzulAPIError(f"Unexpected API error: {e}")

    async def get_customers(
        self,
        access_token: str,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve customers (pessoas) from Conta Azul API v2.

        Uses the /v1/pessoas endpoint with pagination parameters.

        Args:
            access_token: Valid OAuth access token
            search: Optional search term to filter customers (busca)
            limit: Maximum number of customers per page (tamanho_pagina, default: 100)

        Returns:
            List of customer/pessoa dictionaries

        Raises:
            ContaAzulAPIError: If request fails
        """
        all_customers = []
        page = 1
        page_size = min(limit, 100)

        while True:
            params = {
                "pagina": page,
                "tamanho_pagina": page_size
            }
            if search:
                params["busca"] = search

            logger.info(f"Fetching pessoas page {page} (size={page_size})")

            response = await self.make_api_request(
                endpoint="/v1/pessoas",
                access_token=access_token,
                method="GET",
                params=params
            )

            # API v2 may return a list directly or wrapped in a data field
            if isinstance(response, list):
                customers = response
            elif isinstance(response, dict):
                customers = response.get("data", response.get("items", []))
                # If the dict itself looks like it has pessoa fields, wrap it
                if not customers and "id" in response:
                    customers = [response]
            else:
                customers = []

            if not customers:
                break

            all_customers.extend(customers)
            logger.info(f"Page {page}: got {len(customers)} pessoas (total so far: {len(all_customers)})")

            # Stop if we got fewer than page_size (last page) or reached limit
            if len(customers) < page_size or len(all_customers) >= limit:
                break

            page += 1

        logger.info(f"Total pessoas fetched: {len(all_customers)}")
        return all_customers[:limit]

    async def create_customer(
        self,
        access_token: str,
        customer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new customer in Conta Azul.

        Args:
            access_token: Valid OAuth access token
            customer_data: Customer information including name, document, etc.

        Returns:
            Created customer data with ID

        Raises:
            ContaAzulAPIError: If creation fails

        Example:
            >>> service = ContaAzulService()
            >>> customer = await service.create_customer(
            ...     access_token=tokens["access_token"],
            ...     customer_data={
            ...         "name": "João Silva",
            ...         "document": "12345678900",
            ...         "email": "joao@example.com"
            ...     }
            ... )
        """
        return await self.make_api_request(
            endpoint="/v1/pessoas",
            access_token=access_token,
            method="POST",
            json_data=customer_data
        )

    # ─── Financial Endpoints (API v2) ───────────────────────────────────

    @staticmethod
    def _extract_items(response: Any) -> List[Dict[str, Any]]:
        """Extract list-like payloads from heterogeneous Conta Azul responses."""
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in (
                "data",
                "items",
                "content",
                "itens",
                "results",
                "contas",
                "contas_financeiras",
                "contasFinanceiras",
            ):
                value = response.get(key)
                if isinstance(value, list):
                    return value
            if "id" in response:
                return [response]
        return []

    async def get_contas_receber(
        self,
        access_token: str,
        status_filter: Optional[str] = None,
        data_vencimento_inicio: Optional[str] = None,
        data_vencimento_fim: Optional[str] = None,
        data_vencimento_de: Optional[str] = None,
        data_vencimento_ate: Optional[str] = None,
        ids_clientes: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve accounts receivable (contas a receber) from Conta Azul API v2.
        Endpoint: GET /v1/financeiro/eventos-financeiros/contas-a-receber/buscar
        """
        data_de = data_vencimento_de or data_vencimento_inicio
        data_ate = data_vencimento_ate or data_vencimento_fim

        params = {
            "pagina": 1,
            "tamanho_pagina": min(limit, 100)
        }
        if status_filter:
            params["status"] = status_filter
        if data_de:
            params["data_vencimento_de"] = data_de
        if data_ate:
            params["data_vencimento_ate"] = data_ate
        if ids_clientes:
            valid_ids = [str(v).strip() for v in ids_clientes if str(v).strip()]
            if valid_ids:
                params["ids_clientes"] = valid_ids

        logger.info(f"Fetching contas a receber with params: {params}")

        response = await self.make_api_request(
            endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
            access_token=access_token,
            method="GET",
            params=params
        )

        return self._extract_items(response)

    @classmethod
    def normalize_payment_type(cls, payment_type: Any) -> Optional[str]:
        """
        Normalize Conta Azul payment type enums to canonical values.

        Handles legacy values returned by older payloads.
        """
        raw = str(payment_type or "").strip()
        if not raw:
            return None

        upper = raw.upper()
        if upper in {"PIX", cls.LEGACY_PIX_PAYMENT_TYPE, cls.CANONICAL_PIX_PAYMENT_TYPE}:
            return cls.CANONICAL_PIX_PAYMENT_TYPE
        return upper

    async def get_venda_itens_by_sale_id(
        self,
        access_token: str,
        sale_id: str,
        pagina: int = 1,
        tamanho_pagina: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve sale items by sale id.

        Conta Azul enforces a fixed set of page sizes for this endpoint.
        """
        if pagina < 1:
            raise ValueError("pagina must be >= 1")
        if tamanho_pagina not in self.SALES_ITEMS_ALLOWED_PAGE_SIZES:
            allowed = ", ".join(str(v) for v in sorted(self.SALES_ITEMS_ALLOWED_PAGE_SIZES))
            raise ValueError(f"tamanho_pagina must be one of: {allowed}")

        response = await self.make_api_request(
            endpoint=f"/v1/vendas/{sale_id}/itens",
            access_token=access_token,
            method="GET",
            params={"pagina": pagina, "tamanho_pagina": tamanho_pagina},
        )

        items = self._extract_items(response)
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and "id_centro_custo" not in item:
                normalized.append({**item, "id_centro_custo": None})
            elif isinstance(item, dict):
                normalized.append(item)
        return normalized

    async def get_produto_by_id(
        self,
        access_token: str,
        product_id: str,
    ) -> Dict[str, Any]:
        """
        Retrieve product by id.

        Preserves `url_imagem` when returned by Conta Azul.
        """
        response = await self.make_api_request(
            endpoint=f"/v1/produtos/{product_id}",
            access_token=access_token,
            method="GET",
        )

        if isinstance(response, dict) and "url_imagem" not in response:
            response = {**response, "url_imagem": None}
        return response

    async def get_contas_pagar(
        self,
        access_token: str,
        status_filter: Optional[str] = None,
        data_vencimento_inicio: Optional[str] = None,
        data_vencimento_fim: Optional[str] = None,
        data_vencimento_de: Optional[str] = None,
        data_vencimento_ate: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve accounts payable (contas a pagar) from Conta Azul API v2.
        Endpoint: GET /v1/financeiro/eventos-financeiros/contas-a-pagar/buscar
        """
        data_de = data_vencimento_de or data_vencimento_inicio
        data_ate = data_vencimento_ate or data_vencimento_fim

        params = {
            "pagina": 1,
            "tamanho_pagina": min(limit, 100)
        }
        if status_filter:
            params["status"] = status_filter
        if data_de:
            params["data_vencimento_de"] = data_de
        if data_ate:
            params["data_vencimento_ate"] = data_ate

        logger.info(f"Fetching contas a pagar with params: {params}")

        response = await self.make_api_request(
            endpoint="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
            access_token=access_token,
            method="GET",
            params=params
        )

        return self._extract_items(response)

    async def get_contas_financeiras(
        self,
        access_token: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieve financial accounts (contas financeiras) with balances.
        Endpoint: GET /v1/conta-financeira
        """
        logger.info("Fetching contas financeiras")

        # Keep the documented endpoint first, then try legacy variants if empty.
        attempts = [
            ("/v1/conta-financeira", None),
            ("/v1/conta-financeira/busca", {"pagina": 1, "tamanhoPagina": 100}),
            ("/v1/conta-financeira/buscar", {"pagina": 1, "tamanho_pagina": 100}),
            ("/v1/contas-financeiras", None),
        ]

        last_error: Optional[Exception] = None
        for endpoint, params in attempts:
            try:
                request_kwargs: Dict[str, Any] = {
                    "endpoint": endpoint,
                    "access_token": access_token,
                    "method": "GET",
                }
                if params is not None:
                    request_kwargs["params"] = params

                response = await self.make_api_request(
                    **request_kwargs,
                )
                items = self._extract_items(response)
                if items:
                    return items
            except ContaAzulAPIError as exc:
                last_error = exc
                logger.warning(f"Failed contas financeiras endpoint {endpoint}: {exc}")
                continue

        if last_error:
            raise last_error
        return []

    async def get_saldo_conta(
        self,
        access_token: str,
        conta_id: str
    ) -> Dict[str, Any]:
        """
        Get current balance of a specific financial account.
        Endpoint: GET /v1/conta-financeira/{id}/saldo-atual
        """
        response = await self.make_api_request(
            endpoint=f"/v1/conta-financeira/{conta_id}/saldo-atual",
            access_token=access_token,
            method="GET"
        )
        return response

    async def get_contracts(
        self,
        access_token: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve contracts from Conta Azul.

        Args:
            access_token: Valid OAuth access token
            status: Optional contract status filter
            limit: Maximum number of contracts to return (default: 100)

        Returns:
            List of contract dictionaries

        Raises:
            ContaAzulAPIError: If request fails

        Example:
            >>> service = ContaAzulService()
            >>> contracts = await service.get_contracts(
            ...     access_token=tokens["access_token"],
            ...     status="ACTIVE"
            ... )
        """
        params = {"size": limit}
        if status:
            params["status"] = status

        response = await self.make_api_request(
            endpoint="/v1/contracts",
            access_token=access_token,
            method="GET",
            params=params
        )

        return response.get("data", [])
