"""
Unit tests for cash risk trend computation helpers.
"""

from app.services.cash_risk_service import _compute_cash_risk_trend


def test_compute_cash_risk_trend_improving():
    """Risk score drop vs previous day should be classified as improving."""
    snapshot = {
        "snapshot_date": "2026-02-15",
        "risk_score": 31.5,
        "projected_15d": 25000.0,
        "saldo_total": 15000.0,
        "top3_concentration_pct": 58.0,
        "risk_level": "medio",
    }
    history = [
        snapshot,
        {
            "snapshot_date": "2026-02-14",
            "risk_score": 40.0,
            "projected_15d": 22000.0,
            "saldo_total": 13000.0,
            "top3_concentration_pct": 60.5,
            "risk_level": "medio",
        },
        {
            "snapshot_date": "2026-02-13",
            "risk_score": 42.0,
            "projected_15d": 21000.0,
            "saldo_total": 12000.0,
            "top3_concentration_pct": 61.0,
            "risk_level": "alto",
        },
    ]

    trend = _compute_cash_risk_trend(snapshot=snapshot, history=history)

    assert trend["direction"] == "improving"
    assert trend["previous_snapshot_date"] == "2026-02-14"
    assert trend["risk_score_delta"] == -8.5
    assert trend["projected_15d_delta"] == 3000.0
    assert trend["saldo_total_delta"] == 2000.0
    assert trend["top3_concentration_delta_pct"] == -2.5
    assert trend["risk_level_changed"] is False
    assert trend["avg_risk_score_7d"] == 37.83


def test_compute_cash_risk_trend_insufficient_data():
    """When no previous day exists, trend should report insufficient data."""
    snapshot = {
        "snapshot_date": "2026-02-15",
        "risk_score": 35.0,
        "projected_15d": 10000.0,
        "saldo_total": 5000.0,
        "top3_concentration_pct": 50.0,
        "risk_level": "medio",
    }

    trend = _compute_cash_risk_trend(snapshot=snapshot, history=[snapshot])

    assert trend["direction"] == "insufficient_data"
    assert trend["previous_snapshot_date"] is None
    assert trend["risk_score_delta"] is None
    assert trend["projected_15d_delta"] is None
    assert trend["risk_level_changed"] is False
    assert trend["avg_risk_score_7d"] == 35.0

