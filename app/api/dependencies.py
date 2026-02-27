"""
API dependencies for Authentication and Authorization.

Accepted authentication headers:
- X-API-Key: <API_KEY>
- Authorization: Bearer <API_KEY>
"""

import logging
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def _extract_api_key(
    x_api_key: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    """
    Extract API key from accepted headers.

    X-API-Key takes precedence for backward compatibility.
    """
    if x_api_key:
        return x_api_key.strip()

    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    return token.strip()


async def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Validate API key from X-API-Key or Authorization: Bearer headers.

    Uses constant-time comparison to prevent timing attacks.
    """
    provided_key = _extract_api_key(x_api_key=x_api_key, authorization=authorization)
    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Authentication required. Use 'X-API-Key: <API_KEY>' "
                "or 'Authorization: Bearer <API_KEY>'."
            ),
        )

    if not secrets.compare_digest(provided_key, settings.API_SECRET_KEY):
        logger.warning("Rejected request with invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return provided_key


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Backward-compatible alias used by older environments/import paths.
    """
    return await verify_api_key(x_api_key=x_api_key, authorization=authorization)
