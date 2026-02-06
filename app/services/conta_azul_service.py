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
from datetime import datetime, timedelta
import logging
from urllib.parse import urlencode

from app.config import settings

logger = logging.getLogger(__name__)


class ContaAzulError(Exception):
    """Base exception for Conta Azul API errors."""
    pass


class ContaAzulAuthError(ContaAzulError):
    """Exception raised for authentication/authorization errors."""
    pass


class ContaAzulAPIError(ContaAzulError):
    """Exception raised for API request errors."""
    pass


class ContaAzulService:
    """
    Service client for Conta Azul API integration with OAuth 2.0.

    Provides methods for OAuth 2.0 authentication flow and authenticated
    API requests to Conta Azul's accounting platform.

    The client uses credentials from environment variables:
    - CONTA_AZUL_CLIENT_ID: Application client ID
    - CONTA_AZUL_CLIENT_SECRET: Application client secret
    - CONTA_AZUL_REDIRECT_URI: OAuth callback URL
    - CONTA_AZUL_API_BASE_URL: API base URL (default: https://api.contaazul.com)

    Attributes:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        redirect_uri: OAuth redirect URI
        base_url: API base URL
        auth_url: Authorization endpoint URL
        token_url: Token endpoint URL
    """

    # OAuth 2.0 endpoints
    AUTH_ENDPOINT = "/auth/authorize"
    TOKEN_ENDPOINT = "/oauth2/token"

    # Token expiration (60 minutes as per Conta Azul documentation)
    TOKEN_LIFETIME_SECONDS = 3600

    # Available OAuth scopes
    SCOPES = ["sales"]  # Default scope for basic access

    def __init__(self):
        """
        Initialize Conta Azul API client with OAuth credentials.

        Reads configuration from settings (environment variables).
        Raises ValueError if required credentials are not configured.
        """
        try:
            self.client_id = settings.CONTA_AZUL_CLIENT_ID
            self.client_secret = settings.CONTA_AZUL_CLIENT_SECRET
            self.redirect_uri = settings.CONTA_AZUL_REDIRECT_URI
            self.base_url = settings.CONTA_AZUL_API_BASE_URL

            # Construct endpoint URLs
            self.auth_url = f"{self.base_url}{self.AUTH_ENDPOINT}"
            self.token_url = f"{self.base_url}{self.TOKEN_ENDPOINT}"

            logger.info(f"Conta Azul API service initialized with base URL: {self.base_url}")

        except AttributeError as e:
            logger.error(f"Missing required Conta Azul configuration: {e}")
            raise ValueError(
                f"Conta Azul API initialization failed. "
                f"Ensure CONTA_AZUL_CLIENT_ID, CONTA_AZUL_CLIENT_SECRET, "
                f"and CONTA_AZUL_REDIRECT_URI are set: {e}"
            )

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
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
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
        payload = {
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code": code
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info("Exchanging authorization code for tokens")

                response = await client.post(
                    self.token_url,
                    data=payload,
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Token exchange failed: {response.status_code} - {error_detail}")
                    raise ContaAzulAuthError(
                        f"Failed to exchange authorization code: {response.status_code} - {error_detail}"
                    )

                token_data = response.json()

                # Calculate token expiration timestamp
                expires_in = token_data.get("expires_in", self.TOKEN_LIFETIME_SECONDS)
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
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
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.info("Refreshing access token")

                response = await client.post(
                    self.token_url,
                    data=payload,
                    auth=(self.client_id, self.client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Token refresh failed: {response.status_code} - {error_detail}")
                    raise ContaAzulAuthError(
                        f"Failed to refresh access token: {response.status_code} - {error_detail}"
                    )

                token_data = response.json()

                # Calculate token expiration timestamp
                expires_in = token_data.get("expires_in", self.TOKEN_LIFETIME_SECONDS)
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                token_data["expires_at"] = expires_at.isoformat()

                logger.info("Successfully refreshed access token")
                return token_data

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
            # Add 60 second buffer to avoid race conditions
            return datetime.utcnow() >= (expiration - timedelta(seconds=60))
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
        url = f"{self.base_url}{endpoint}"
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
                    error_detail = response.text
                    logger.error(f"API request failed: {response.status_code} - {error_detail}")
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
        Retrieve customers from Conta Azul.

        Args:
            access_token: Valid OAuth access token
            search: Optional search term to filter customers
            limit: Maximum number of customers to return (default: 100)

        Returns:
            List of customer dictionaries

        Raises:
            ContaAzulAPIError: If request fails

        Example:
            >>> service = ContaAzulService()
            >>> customers = await service.get_customers(
            ...     access_token=tokens["access_token"],
            ...     search="João Silva"
            ... )
        """
        params = {"size": limit}
        if search:
            params["search"] = search

        response = await self.make_api_request(
            endpoint="/v1/customers",
            access_token=access_token,
            method="GET",
            params=params
        )

        return response.get("data", [])

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
            endpoint="/v1/customers",
            access_token=access_token,
            method="POST",
            json_data=customer_data
        )

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
