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

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import logging
import secrets
from sqlalchemy.orm import Session

from app.services.conta_azul_service import ContaAzulService, ContaAzulAuthError
from app.database import get_db
from app.models.integration_token import IntegrationToken

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


# Pydantic schemas for request/response validation
class OAuthStatusResponse(BaseModel):
    """Response with OAuth connection status"""
    service: str = Field(..., description="Service name (e.g., 'conta_azul')")
    connected: bool = Field(..., description="Whether OAuth connection is active")
    expires_at: Optional[datetime] = Field(None, description="Token expiration timestamp")
    created_at: Optional[datetime] = Field(None, description="Connection creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "service": "conta_azul",
                "connected": True,
                "expires_at": "2026-02-06T18:00:00Z",
                "created_at": "2026-02-06T12:00:00Z"
            }
        }


class OAuthCallbackResponse(BaseModel):
    """Response after successful OAuth callback"""
    message: str = Field(..., description="Success message")
    service: str = Field(..., description="Service name")
    expires_at: str = Field(..., description="Token expiration timestamp")
    created_at: datetime = Field(..., description="Connection creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Successfully connected to Conta Azul",
                "service": "conta_azul",
                "expires_at": "2026-02-06T18:00:00Z",
                "created_at": "2026-02-06T12:00:00Z"
            }
        }


@router.get("/conta-azul/authorize", status_code=status.HTTP_302_FOUND)
async def conta_azul_authorize():
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

        # Generate random state for CSRF protection
        # In production, store this state in session or cache and verify in callback
        state = secrets.token_urlsafe(32)

        # Get authorization URL
        authorization_url = service.get_authorization_url(
            state=state,
            scope=["sales"]  # Request sales scope for customer and contract access
        )

        logger.info(f"Redirecting to Conta Azul authorization page with state: {state[:10]}...")

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

    # TODO: In production, verify state token against stored value for CSRF protection
    # For now, we just log it for debugging
    logger.info(f"Received OAuth callback with state: {state[:10] if state else 'None'}...")

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
            from datetime import timedelta
            expires_at = datetime.utcnow() + timedelta(hours=1)
            logger.warning("Could not parse expires_at, using default 1 hour")

        # Store tokens in database (upsert pattern)
        now = datetime.utcnow()
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
            detail=f"Failed to authenticate with Conta Azul: {str(e)}"
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
async def conta_azul_status(db: Session = Depends(get_db)):
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
