"""
OAuth State Database Model

Stores OAuth CSRF state tokens with expiration in the database so validation
works across process restarts and multiple workers.
"""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class OAuthState(Base):
    """One-time OAuth state token used for CSRF protection."""

    __tablename__ = "oauth_states"

    state = Column(
        String(128),
        primary_key=True,
        nullable=False,
        comment="One-time OAuth state token",
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Expiration timestamp for state token",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="State creation timestamp",
    )

    def __repr__(self) -> str:
        return f"<OAuthState(state='{self.state[:8]}...', expires_at='{self.expires_at}')>"
