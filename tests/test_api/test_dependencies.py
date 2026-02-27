"""
Tests for API authentication dependencies.
"""

import pytest
from fastapi import HTTPException

from app.api.dependencies import require_api_key, verify_api_key
from app.config import settings


@pytest.mark.asyncio
async def test_verify_api_key_accepts_x_api_key():
    """X-API-Key header should authenticate successfully."""
    result = await verify_api_key(
        x_api_key=settings.API_SECRET_KEY,
        authorization=None,
    )
    assert result == settings.API_SECRET_KEY


@pytest.mark.asyncio
async def test_verify_api_key_accepts_bearer_authorization():
    """Authorization Bearer header should authenticate successfully."""
    result = await verify_api_key(
        x_api_key=None,
        authorization=f"Bearer {settings.API_SECRET_KEY}",
    )
    assert result == settings.API_SECRET_KEY


@pytest.mark.asyncio
async def test_verify_api_key_prioritizes_x_api_key_over_authorization():
    """X-API-Key should have precedence when both headers are present."""
    result = await verify_api_key(
        x_api_key=settings.API_SECRET_KEY,
        authorization="Bearer invalid-token",
    )
    assert result == settings.API_SECRET_KEY


@pytest.mark.asyncio
async def test_verify_api_key_requires_one_supported_header():
    """Missing/invalid headers should return 401 with guidance."""
    with pytest.raises(HTTPException) as exc:
        await verify_api_key(
            x_api_key=None,
            authorization="Basic abc123",
        )

    assert exc.value.status_code == 401
    assert "X-API-Key" in str(exc.value.detail)
    assert "Authorization" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_require_api_key_alias_works():
    """Legacy require_api_key alias should route to the same validation."""
    result = await require_api_key(
        x_api_key=None,
        authorization=f"Bearer {settings.API_SECRET_KEY}",
    )
    assert result == settings.API_SECRET_KEY
