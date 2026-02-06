"""
Integration Token Database Model

This module defines the IntegrationToken model for storing OAuth 2.0 access and refresh tokens
for external service integrations. Primarily used for Conta Azul accounting platform OAuth flow,
but designed to be extensible for future integrations (e.g., Autentique, other services).

The model stores tokens with expiration tracking and supports automatic token refresh workflows.
Each service can have one active token stored (enforced by unique constraint on service field).

Security Note: In production environments, consider encrypting the access_token and refresh_token
fields using SQLAlchemy encryption libraries (e.g., sqlalchemy-utils with cryptography).
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from app.database import Base


class IntegrationToken(Base):
    """
    Integration token model for OAuth 2.0 token storage.

    Stores OAuth access and refresh tokens for external service integrations.
    Supports automatic token expiration checking and refresh workflows.
    Each service is limited to one active token (unique constraint on service field).

    Attributes:
        id: Primary key, auto-incrementing integer
        service: Service identifier (e.g., "conta_azul", "autentique") - unique per service
        access_token: OAuth 2.0 access token for API authentication (consider encryption in production)
        refresh_token: OAuth 2.0 refresh token for obtaining new access tokens (optional)
        expires_at: Token expiration timestamp (UTC) for automatic refresh logic
        created_at: Timestamp when token was first created (auto-generated)
        updated_at: Timestamp when token was last refreshed/updated (auto-updated)

    Indexes:
        - service: For fast service-specific token lookups (unique constraint)

    Methods:
        is_expired(): Check if token is currently expired

    Usage:
        # Store a new OAuth token
        token = IntegrationToken(
            service="conta_azul",
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            refresh_token="def50200abc123...",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db.add(token)
        db.commit()

        # Check if token needs refresh
        token = db.query(IntegrationToken).filter_by(service="conta_azul").first()
        if token.is_expired():
            # Trigger token refresh logic
            pass

        # Update existing token (upsert pattern)
        existing = db.query(IntegrationToken).filter_by(service="conta_azul").first()
        if existing:
            existing.access_token = new_access_token
            existing.expires_at = new_expires_at
        else:
            db.add(IntegrationToken(service="conta_azul", ...))
        db.commit()
    """
    __tablename__ = "integration_tokens"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Service identification
    service = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Service identifier (e.g., 'conta_azul', 'autentique')"
    )

    # OAuth 2.0 tokens (consider encryption in production)
    access_token = Column(
        String(1000),
        nullable=False,
        comment="OAuth 2.0 access token - consider encryption in production"
    )
    refresh_token = Column(
        String(1000),
        nullable=True,
        comment="OAuth 2.0 refresh token for obtaining new access tokens"
    )

    # Token expiration management
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token expiration timestamp (UTC) for refresh logic"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Token creation timestamp"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last token update/refresh timestamp"
    )

    def is_expired(self, buffer_minutes: int = 5) -> bool:
        """
        Check if token is currently expired or about to expire.

        Args:
            buffer_minutes: Safety buffer in minutes before actual expiration (default: 5).
                          This prevents edge-case failures during API requests.

        Returns:
            bool: True if token is expired or within buffer window, False otherwise.

        Usage:
            token = db.query(IntegrationToken).filter_by(service="conta_azul").first()
            if token.is_expired():
                # Refresh token before making API call
                refresh_oauth_token(token)
        """
        buffer = timedelta(minutes=buffer_minutes)
        return datetime.utcnow() >= (self.expires_at - buffer)

    def __repr__(self) -> str:
        """String representation of IntegrationToken instance for debugging."""
        return (
            f"<IntegrationToken(id={self.id}, service='{self.service}', "
            f"expires_at='{self.expires_at}')>"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "expired" if self.is_expired() else "valid"
        return f"{self.service} token ({status}, expires: {self.expires_at})"
