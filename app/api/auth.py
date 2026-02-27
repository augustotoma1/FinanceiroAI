"""
OAuth Authentication API Endpoints

This module provides FastAPI endpoints for OAuth 2.0 authentication flows
with external services. Currently supports Conta Azul accounting platform
integration.

Endpoints:
- GET /conta-azul/authorize - Initiate OAuth flow and redirect to Conta Azul
- GET /conta-azul/callback - Handle OAuth callback and exchange code for tokens
- GET /conta-azul/status - Check current OAuth connection status
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import secrets
from sqlalchemy.orm import Session

from app.services.conta_azul_service import ContaAzulService, ContaAzulAuthError
from app.services.signature_sync_service import (
    sync_signatures_for_document,
    sync_signatures_from_autentique,
)
from app.config import settings
from app.database import get_db
from app.models.integration_token import IntegrationToken
from app.models.oauth_state import OAuthState
from app.api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()

_STATE_TTL_SECONDS = 600  # 10 minutes — enough time for user to approve on Conta Azul


def _store_oauth_state(db: Session, state: str) -> None:
    """Persist OAuth state token with TTL in database for multi-worker safety."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=_STATE_TTL_SECONDS)
    try:
        # Best-effort cleanup to keep table bounded.
        db.query(OAuthState).filter(OAuthState.expires_at < now).delete(
            synchronize_session=False
        )
        db.add(OAuthState(state=state, expires_at=expires_at))
        db.commit()
    except Exception:
        db.rollback()
        raise


def _validate_and_consume_oauth_state(db: Session, state: str | None) -> bool:
    """Validate state token exists and hasn't expired, then consume it (one-time use)."""
    if not state:
        return False

    now = datetime.now(timezone.utc)
    try:
        db.query(OAuthState).filter(OAuthState.expires_at < now).delete(
            synchronize_session=False
        )
        state_record = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not state_record:
            db.commit()
            return False

        expires_at = state_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        is_valid = expires_at > now
        db.delete(state_record)
        db.commit()
        return is_valid
    except Exception:
        db.rollback()
        raise


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_document_ids(payload: object) -> list[str]:
    """
    Extract candidate document IDs from flexible webhook payloads.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def _push(value: object) -> None:
        text = _as_text(value)
        if not text or text in seen:
            return
        seen.add(text)
        ids.append(text)

    if not isinstance(payload, dict):
        return ids

    _push(payload.get("document_id"))
    _push(payload.get("documentId"))
    _push(payload.get("id"))

    data = payload.get("data")
    if isinstance(data, dict):
        _push(data.get("document_id"))
        _push(data.get("documentId"))
        _push(data.get("id"))
        nested_doc = data.get("document")
        if isinstance(nested_doc, dict):
            _push(nested_doc.get("id"))

    document = payload.get("document")
    if isinstance(document, dict):
        _push(document.get("id"))

    documents = payload.get("documents")
    if isinstance(documents, list):
        for item in documents:
            if isinstance(item, dict):
                _push(item.get("id"))

    return ids


def _extract_webhook_secret(request: Request) -> str:
    """
    Resolve webhook secret from headers/query.
    """
    candidates = [
        request.headers.get("x-webhook-token"),
        request.headers.get("x-autentique-token"),
        request.query_params.get("token"),
    ]

    auth_header = _as_text(request.headers.get("authorization"))
    if auth_header.lower().startswith("bearer "):
        candidates.append(auth_header[7:].strip())

    for value in candidates:
        token = _as_text(value)
        if token:
            return token
    return ""


# Pydantic schemas for request/response validation
class OAuthStatusResponse(BaseModel):
    """Response with OAuth connection status"""
    service: str = Field(..., description="Service name (e.g., 'conta_azul')")
    connected: bool = Field(..., description="Whether OAuth connection is active")
    expires_at: Optional[datetime] = Field(None, description="Token expiration timestamp")
    created_at: Optional[datetime] = Field(None, description="Connection creation timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "service": "conta_azul",
            "connected": True,
            "expires_at": "2026-02-06T18:00:00Z",
            "created_at": "2026-02-06T12:00:00Z"
        }
    })


class OAuthCallbackResponse(BaseModel):
    """Response after successful OAuth callback"""
    message: str = Field(..., description="Success message")
    service: str = Field(..., description="Service name")
    expires_at: str = Field(..., description="Token expiration timestamp")
    created_at: datetime = Field(..., description="Connection creation timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "Successfully connected to Conta Azul",
            "service": "conta_azul",
            "expires_at": "2026-02-06T18:00:00Z",
            "created_at": "2026-02-06T12:00:00Z"
        }
    })


@router.get("/conta-azul/authorize", status_code=status.HTTP_302_FOUND)
async def conta_azul_authorize(db: Session = Depends(get_db)):
    """
    Initiate OAuth 2.0 authorization flow with Conta Azul.

    Redirects the user to Conta Azul's authorization page where they will
    grant access to their account. After granting access, Conta Azul will
    redirect back to the callback endpoint with an authorization code.

    Returns:
        RedirectResponse: 302 redirect to Conta Azul authorization page

    Raises:
        HTTPException 503: If Conta Azul service is unavailable

    Flow:
        1. User clicks "Connect Conta Azul" in your application
        2. This endpoint generates authorization URL with CSRF state token
        3. User is redirected to Conta Azul to grant permissions
        4. User approves and is redirected to /callback with code parameter
        5. Callback endpoint exchanges code for access token

    Example:
        GET /api/auth/conta-azul/authorize
        Response: 302 Redirect to https://api.contaazul.com/auth/authorize?...
    """
    try:
        # Initialize Conta Azul service
        service = ContaAzulService()

        # Generate random state for CSRF protection and store it
        state = secrets.token_urlsafe(32)
        _store_oauth_state(db, state)

        # Get authorization URL with Cognito scopes
        authorization_url = service.get_authorization_url(
            state=state
        )

        logger.info("Redirecting to Conta Azul authorization page")

        # Redirect user to Conta Azul authorization page
        return RedirectResponse(
            url=authorization_url,
            status_code=status.HTTP_302_FOUND
        )

    except ValueError as e:
        logger.error(f"Configuration error for Conta Azul OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Conta Azul integration not properly configured: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error initiating Conta Azul OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Conta Azul authorization"
        )


@router.get("/conta-azul/callback", response_model=OAuthCallbackResponse, status_code=status.HTTP_200_OK)
async def conta_azul_callback(
    code: str = Query(..., description="Authorization code from Conta Azul"),
    state: Optional[str] = Query(None, description="CSRF protection state token"),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth 2.0 callback from Conta Azul.

    Receives the authorization code from Conta Azul, exchanges it for
    access and refresh tokens, and stores them securely in the database.

    Args:
        code: Authorization code from Conta Azul OAuth redirect
        state: CSRF state token (should match the one sent in authorize)
        db: Database session dependency

    Returns:
        OAuthCallbackResponse: Success message with connection details

    Raises:
        HTTPException 400: If authorization code is missing or invalid
        HTTPException 401: If token exchange fails (authentication error)
        HTTPException 500: If database storage fails

    Example:
        GET /api/auth/conta-azul/callback?code=AUTH_CODE_123&state=RANDOM_STATE
        Response:
        {
            "message": "Successfully connected to Conta Azul",
            "service": "conta_azul",
            "expires_at": "2026-02-06T18:00:00Z",
            "created_at": "2026-02-06T12:00:00Z"
        }
    """
    # Validate authorization code parameter
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required"
        )

    # Validate state token for CSRF protection (one-time use)
    if not _validate_and_consume_oauth_state(db, state):
        logger.warning("OAuth callback with invalid or expired state token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state token. Please restart the authorization flow."
        )

    try:
        # Initialize Conta Azul service
        service = ContaAzulService()

        # Exchange authorization code for tokens
        logger.info("Exchanging authorization code for access token")
        token_data = await service.exchange_code_for_token(code=code)

        # Extract token information
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_at_str = token_data.get("expires_at")

        if not access_token or not refresh_token:
            logger.error("Token response missing required fields")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid token response from Conta Azul"
            )

        # Parse expiration timestamp
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
        except (ValueError, TypeError):
            # Fallback to 1 hour from now if parsing fails
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            logger.warning("Could not parse expires_at, using default 1 hour")

        # Store tokens in database (upsert pattern)
        now = datetime.now(timezone.utc)
        existing_token = db.query(IntegrationToken).filter_by(service="conta_azul").first()

        if existing_token:
            # Update existing token
            logger.info("Updating existing Conta Azul OAuth tokens")
            existing_token.access_token = access_token
            existing_token.refresh_token = refresh_token
            existing_token.expires_at = expires_at
            existing_token.updated_at = now
            token_record = existing_token
        else:
            # Create new token record
            logger.info("Creating new Conta Azul OAuth token record")
            token_record = IntegrationToken(
                service="conta_azul",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                created_at=now,
                updated_at=now
            )
            db.add(token_record)

        # Commit to database
        db.commit()
        db.refresh(token_record)

        logger.info("Successfully stored Conta Azul OAuth tokens in database")

        return OAuthCallbackResponse(
            message="Successfully connected to Conta Azul",
            service="conta_azul",
            expires_at=expires_at_str,
            created_at=token_record.created_at
        )

    except ContaAzulAuthError as e:
        logger.error(f"Authentication error during OAuth callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with Conta Azul"
        )
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        # Rollback database changes on error
        db.rollback()
        logger.error(f"Unexpected error during OAuth callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete Conta Azul authentication"
        )


@router.get("/conta-azul/status", response_model=OAuthStatusResponse, status_code=status.HTTP_200_OK)
async def conta_azul_status(
    _api_key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Check current Conta Azul OAuth connection status.

    Returns information about whether a valid OAuth connection exists,
    when it was created, and when the access token will expire.

    Args:
        db: Database session dependency

    Returns:
        OAuthStatusResponse: Connection status information

    Example:
        GET /api/auth/conta-azul/status
        Response:
        {
            "service": "conta_azul",
            "connected": true,
            "expires_at": "2026-02-06T18:00:00Z",
            "created_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        # Query for existing Conta Azul token
        token_record = db.query(IntegrationToken).filter_by(service="conta_azul").first()

        if not token_record:
            # No connection exists
            return OAuthStatusResponse(
                service="conta_azul",
                connected=False,
                expires_at=None,
                created_at=None
            )

        # Check if token is expired
        is_expired = token_record.is_expired()

        return OAuthStatusResponse(
            service="conta_azul",
            connected=not is_expired,
            expires_at=token_record.expires_at,
            created_at=token_record.created_at
        )

    except Exception as e:
        logger.error(f"Error checking Conta Azul OAuth status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check OAuth connection status"
        )


@router.post("/autentique/webhook", status_code=status.HTTP_200_OK)
async def autentique_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive Autentique webhook notifications and trigger signature reconciliation.
    """
    if not bool(getattr(settings, "AUTENTIQUE_WEBHOOK_ENABLED", True)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autentique webhook is disabled",
        )

    expected_secret = _as_text(getattr(settings, "AUTENTIQUE_WEBHOOK_SECRET", ""))
    if expected_secret:
        provided_secret = _extract_webhook_secret(request)
        if not secrets.compare_digest(provided_secret, expected_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    document_ids = _extract_document_ids(payload)
    results: list[dict[str, object]] = []

    if document_ids:
        for document_id in document_ids:
            result = await sync_signatures_for_document(db, document_id=document_id)
            results.append(
                {
                    "document_id": document_id,
                    "success": bool(result.get("success")),
                    "processed_contracts": int(result.get("processed_contracts", 0)),
                    "error_count": int(result.get("error_count", 0)),
                    "skipped": bool(result.get("skipped", False)),
                    "reason": result.get("reason"),
                }
            )

        return {
            "ok": True,
            "mode": "document",
            "documents": results,
            "count": len(results),
        }

    fallback_max = max(
        1,
        int(getattr(settings, "AUTENTIQUE_WEBHOOK_FALLBACK_MAX_CONTRACTS", 20)),
    )
    fallback_result = await sync_signatures_from_autentique(
        db,
        max_contracts=fallback_max,
        only_open_contracts=True,
    )
    return {
        "ok": bool(fallback_result.get("success") or fallback_result.get("partial_success")),
        "mode": "fallback",
        "max_contracts": fallback_max,
        "processed_contracts": int(fallback_result.get("processed_contracts", 0)),
        "error_count": int(fallback_result.get("error_count", 0)),
    }
