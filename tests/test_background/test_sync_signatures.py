import pytest

import app.background.sync_signatures as sync_signatures


class _DummySession:
    def close(self):
        return None


@pytest.mark.asyncio
async def test_sync_signatures_job_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(sync_signatures.settings, "AUTENTIQUE_SIGNATURE_SYNC_ENABLED", False)

    result = await sync_signatures.sync_signatures_job()

    assert result["success"] is True
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_sync_signatures_job_calls_service(monkeypatch):
    monkeypatch.setattr(sync_signatures.settings, "AUTENTIQUE_SIGNATURE_SYNC_ENABLED", True)
    monkeypatch.setattr(sync_signatures.settings, "AUTENTIQUE_API_KEY", "key")
    monkeypatch.setattr(sync_signatures.settings, "AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS", 25)
    monkeypatch.setattr(sync_signatures.settings, "AUTENTIQUE_SIGNATURE_SYNC_ONLY_OPEN", True)
    monkeypatch.setattr(sync_signatures, "SessionLocal", lambda: _DummySession())

    async def _fake_sync(db, *, max_contracts, only_open_contracts):
        assert isinstance(db, _DummySession)
        assert max_contracts == 25
        assert only_open_contracts is True
        return {
            "success": True,
            "processed_contracts": 3,
            "created_signatures": 1,
            "updated_signatures": 2,
            "updated_contracts": 1,
            "error_count": 0,
        }

    monkeypatch.setattr(sync_signatures, "sync_signatures_from_autentique", _fake_sync)

    result = await sync_signatures.sync_signatures_job()

    assert result["success"] is True
    assert result["processed_contracts"] == 3
