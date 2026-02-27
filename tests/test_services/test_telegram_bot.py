"""
Unit tests for Telegram bot helper functions.
"""

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import pytest

from app.services.telegram_bot import (
    _build_operacao_dia_lines,
    _client_sync_freshness_line,
    _build_email_billing_alert_lines,
    _build_cfo_alert_flags,
    _build_cfo_action_plan,
    _build_conta_azul_reconnect_url,
    _extract_balance_value,
    _financial_sync_freshness,
    _format_cfo_trend_lines,
    _format_expiry_eta,
    _is_affirmative_answer,
    _is_negative_answer,
    _is_skip_answer,
    _normalize_client_tax_id,
    _parse_period_input,
    _parse_contract_template_args,
    _period_prompt_text,
    _normalize_contract_template_name,
    _telegram_alert_chat_id,
)


def test_parse_period_input_numeric_days():
    """Numeric input should map to upcoming N days."""
    data_de, data_ate, label = _parse_period_input("7")
    today = datetime.now(timezone.utc).date()

    assert data_de == today.isoformat()
    assert data_ate == (today + timedelta(days=7)).isoformat()
    assert label == "proximos 7 dias"


def test_parse_period_input_custom_iso_range():
    """Custom date range must be preserved as provided."""
    data_de, data_ate, label = _parse_period_input("2026-02-01 2026-02-28")

    assert data_de == "2026-02-01"
    assert data_ate == "2026-02-28"
    assert label == "2026-02-01 a 2026-02-28"


def test_normalize_client_tax_id_keeps_digits_and_truncates():
    """Tax id normalizer should keep only digits and respect varchar(20)."""
    assert _normalize_client_tax_id("12.345.678/0001-99") == "12345678000199"
    assert _normalize_client_tax_id("ABC123") == "123"
    assert _normalize_client_tax_id("1" * 40) == "1" * 20


def test_onboarding_yes_no_skip_parsers():
    """Onboarding parser helpers should recognize common answers."""
    assert _is_affirmative_answer("SIM")
    assert _is_negative_answer("não")
    assert _is_skip_answer("pular")


def test_normalize_contract_template_name_valid_default():
    """Template normalizer should fallback to default template when empty."""
    assert _normalize_contract_template_name("") == "default_contract.html"


def test_normalize_contract_template_name_rejects_path_traversal():
    """Template normalizer must reject path traversal values."""
    with pytest.raises(ValueError):
        _normalize_contract_template_name("../secret.html")


def test_parse_contract_template_args_with_custom_template():
    """Command arg parser should extract contract id and optional template."""
    contract_id, template_name = _parse_contract_template_args(
        ["42", "default_contract.html"],
        "preview_contrato",
    )
    assert contract_id == 42
    assert template_name == "default_contract.html"


def test_extract_balance_value_nested_known_key():
    """Known nested key should be parsed with BR decimal format."""
    payload = {"saldo": {"saldoDisponivel": "1.234,56"}}
    assert _extract_balance_value(payload) == 1234.56


def test_extract_balance_value_recursive_candidate():
    """Recursive extraction should find balance in non-standard nested keys."""
    payload = {"contaFinanceira": {"resultadoSaldo": {"valor": "980.40"}}}
    assert _extract_balance_value(payload) == 980.40


def test_extract_balance_value_missing_fields_returns_zero():
    """Missing balance-like fields must return zero."""
    payload = {"id": "abc", "nome": "Conta Teste"}
    assert _extract_balance_value(payload) == 0.0


def test_format_expiry_eta_variants():
    """Expiry ETA formatting should follow minute/hour/day buckets."""
    assert _format_expiry_eta(-1) == "expirado"
    assert _format_expiry_eta(120) == "expira em 2 min"
    assert _format_expiry_eta(7200) == "expira em 2h"
    assert _format_expiry_eta(172800) == "expira em 2d"


def test_build_reconnect_url_standard_callback():
    """Standard callback URL should map to authorize endpoint on same host."""
    redirect_uri = "https://api.satec.digital/api/auth/conta-azul/callback"
    assert (
        _build_conta_azul_reconnect_url(redirect_uri)
        == "https://api.satec.digital/api/auth/conta-azul/authorize"
    )


def test_build_reconnect_url_with_path_prefix():
    """Deployments with path prefix should preserve that prefix."""
    redirect_uri = "https://corp.example.com/financeiro/api/auth/conta-azul/callback"
    assert (
        _build_conta_azul_reconnect_url(redirect_uri)
        == "https://corp.example.com/financeiro/api/auth/conta-azul/authorize"
    )


def test_build_reconnect_url_invalid_input_uses_relative_fallback():
    """Malformed redirect URI should fallback to a safe relative authorize path."""
    assert _build_conta_azul_reconnect_url("") == "/api/auth/conta-azul/authorize"


def test_format_cfo_trend_lines_improving():
    """Trend formatter should include deltas for improving direction."""
    trend = {
        "direction": "improving",
        "risk_score_delta": -4.25,
        "projected_15d_delta": 3200.0,
        "top3_concentration_delta_pct": -1.5,
        "avg_risk_score_7d": 34.8,
    }

    lines = _format_cfo_trend_lines(trend)
    text = "\n".join(lines)

    assert "Tendência 7d: *MELHORANDO*" in text
    assert "Δ Score de risco: -4.25 pts" in text
    assert "Δ Projeção 15d: +R$ 3.200,00" in text
    assert "Δ Concentração Top 3: -1.50 pp" in text
    assert "Média score 7d: +34.80" in text


def test_format_cfo_trend_lines_insufficient_data():
    """Trend formatter should degrade gracefully when trend is unavailable."""
    lines = _format_cfo_trend_lines(None)
    assert "dados insuficientes" in "\n".join(lines).lower()


def test_format_cfo_trend_lines_plain_text_mode():
    """Plain-text mode should avoid markdown markers for daily alerts."""
    trend = {"direction": "stable"}
    lines = _format_cfo_trend_lines(trend, markdown=False)
    assert "*ESTÁVEL*" not in "\n".join(lines)
    assert "ESTÁVEL" in "\n".join(lines)


def test_build_cfo_action_plan_worsening_and_targets_off():
    """Action plan should prioritize execution when trend/risk/targets are bad."""
    actions = _build_cfo_action_plan(
        risk_level="alto",
        trend_direction="worsening",
        inadimplencia_ok=False,
        concentracao_ok=False,
    )
    text = "\n".join(actions).lower()

    assert "comitê de caixa" in text
    assert "régua de cobrança" in text
    assert "diversificação" in text


def test_build_cfo_action_plan_low_risk_stable():
    """Healthy context should still return a maintenance action."""
    actions = _build_cfo_action_plan(
        risk_level="baixo",
        trend_direction="stable",
        inadimplencia_ok=True,
        concentracao_ok=True,
    )
    assert len(actions) >= 1
    assert "rotina diária" in actions[0].lower()


def test_build_cfo_alert_flags_high_risk_context():
    """Alert flags should include all breached conditions in stressed context."""
    flags = _build_cfo_alert_flags(
        risk_level="alto",
        projected_15d=-1500.0,
        inadimplencia_pct=14.2,
        meta_inadimplencia_pct=5.0,
        top3_concentration_pct=72.0,
        meta_concentracao_top3_pct=60.0,
        trend_direction="worsening",
        saldos_all_zero=True,
    )
    text = "\n".join(flags).lower()

    assert "caixa projetado 15d negativo" in text
    assert "inadimplência acima da meta" in text
    assert "concentração top 3 acima da meta" in text
    assert "tendência de risco piorando" in text
    assert "saldo r$ 0,00" in text


def test_build_cfo_alert_flags_healthy_context():
    """Healthy context should not generate executive alert flags."""
    flags = _build_cfo_alert_flags(
        risk_level="baixo",
        projected_15d=5000.0,
        inadimplencia_pct=2.0,
        meta_inadimplencia_pct=5.0,
        top3_concentration_pct=35.0,
        meta_concentracao_top3_pct=60.0,
        trend_direction="stable",
        saldos_all_zero=False,
    )
    assert flags == []


def test_period_prompt_text_supports_sync_financeiro():
    """Sync financeiro flow should ask period using dedicated label."""
    prompt = _period_prompt_text("sync_financeiro").lower()
    assert "sincronizacao financeira" in prompt


def test_financial_sync_freshness_stale_and_recent():
    """Freshness helper should classify stale and recent sync windows."""
    assert "sem histórico" in (_financial_sync_freshness(None) or "").lower()
    assert "defasada" in (_financial_sync_freshness("2026-01-01T00:00:00+00:00") or "").lower()
    assert "recente" in (_financial_sync_freshness(datetime.now(timezone.utc).isoformat()) or "").lower()


def test_client_sync_freshness_line_variants():
    """Client sync freshness helper should map all status variants."""
    assert "defasada" in _client_sync_freshness_line("stale", 8.2).lower()
    assert "atenção" in _client_sync_freshness_line("warning", 3.1).lower()
    assert "recente" in _client_sync_freshness_line("fresh", 0.4).lower()
    assert "sem histórico" in _client_sync_freshness_line("missing", None).lower()


def test_build_email_billing_alert_lines_skipped():
    """Email billing alert should explain skipped campaign reason."""
    lines = _build_email_billing_alert_lines(
        {"success": True, "skipped": True, "reason": "EMAIL_BILLING_ENABLED is false"},
        now=datetime(2026, 2, 15, tzinfo=timezone.utc),
    )
    text = "\n".join(lines).lower()
    assert "campanha não executada" in text
    assert "email_billing_enabled is false" in text


def test_build_email_billing_alert_lines_success_with_test_mode():
    """Alert lines should include mode, totals, test recipients and no-error marker."""
    lines = _build_email_billing_alert_lines(
        {
            "provider": "sendgrid",
            "dry_run": False,
            "eligible_clients": 3,
            "eligible_records": 7,
            "emails_sent": 2,
            "emails_dry_run": 0,
            "emails_failed": 0,
            "level_counts": {"1": 1, "2": 1, "3": 1},
            "test_mode": True,
            "test_recipients": ["a@example.com", "b@example.com"],
            "errors": [],
            "duration_seconds": 1.27,
        },
        now=datetime(2026, 2, 15, tzinfo=timezone.utc),
    )
    text = "\n".join(lines).lower()
    assert "execução: sendgrid/real" in text
    assert "clientes elegíveis: 3" in text
    assert "enviados: 2" in text
    assert "destinos de teste" in text
    assert "resultado: campanha concluída sem erros" in text


def test_telegram_alert_chat_id_format():
    """Persistent alert chat key should use tga- prefix and keep deterministic value."""
    assert _telegram_alert_chat_id(123456789) == "tga-123456789"


@pytest.mark.asyncio
async def test_build_operacao_dia_lines_happy_path(monkeypatch):
    """Daily operation summary should include sync, risk, billing and lifecycle sections."""
    from app.services import telegram_bot as bot

    async def _fake_get_sync_status():
        return {
            "total_clients": 201,
            "synced_clients": 201,
            "sync_freshness": "fresh",
            "hours_since_last_sync": 0.3,
        }

    async def _fake_get_financial_sync_status():
        return {
            "total_records": 1131,
            "receivable_records": 595,
            "payable_records": 536,
            "overdue_records": 147,
            "last_sync_time": datetime.now(timezone.utc).isoformat(),
        }

    async def _fake_get_token():
        return "token_ok", None

    async def _fake_build_cfo_snapshot(_access_token: str):
        return {
            "projected_15d": 59981.98,
            "risk": {"level": "medio"},
            "concentration": {"top_pct": 70.3},
            "receber_summary_30": {"total_aberto": 100000.0, "total_atrasado": 14700.0},
        }

    async def _fake_run_billing_email_campaign(dry_run: bool = True):
        assert dry_run is True
        return {
            "eligible_clients": 17,
            "eligible_records": 19,
            "level_counts": {"1": 0, "2": 16, "3": 1},
        }

    def _fake_trend(_history_days: int = 7):
        return {"direction": "stable"}

    def _fake_lifecycle_snapshot(_db, days_ahead: int):
        assert days_ahead == 30
        return {
            "monitored_total": 1,
            "overdue": [],
            "expiring_soon": [{"contract_number": "PILOTO-001", "days_to_end": 10}],
            "missing_end_date": [],
        }

    @contextmanager
    def _fake_db_scope():
        yield object()

    monkeypatch.setattr("app.background.sync_clients.get_sync_status", _fake_get_sync_status)
    monkeypatch.setattr(
        "app.background.sync_financial.get_financial_sync_status",
        _fake_get_financial_sync_status,
    )
    monkeypatch.setattr("app.services.telegram_bot._get_conta_azul_token", _fake_get_token)
    monkeypatch.setattr("app.services.telegram_bot._build_cfo_snapshot", _fake_build_cfo_snapshot)
    monkeypatch.setattr("app.services.telegram_bot._load_cash_risk_trend", _fake_trend)
    monkeypatch.setattr(
        "app.services.email_billing_service.run_billing_email_campaign",
        _fake_run_billing_email_campaign,
    )
    monkeypatch.setattr(
        "app.services.contract_lifecycle_service.build_contract_lifecycle_snapshot",
        _fake_lifecycle_snapshot,
    )
    monkeypatch.setattr("app.services.telegram_bot._db_session_scope", _fake_db_scope)
    monkeypatch.setattr(bot.settings, "EMAIL_BILLING_ENABLED", True)
    monkeypatch.setattr(bot.settings, "EMAIL_BILLING_PROVIDER", "sendgrid")
    monkeypatch.setattr(bot.settings, "EMAIL_BILLING_HOUR", 9)
    monkeypatch.setattr(bot.settings, "EMAIL_BILLING_MINUTE", 0)
    monkeypatch.setattr(bot.settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False)
    monkeypatch.setattr(bot.settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30)

    lines = await _build_operacao_dia_lines()
    text = "\n".join(lines).lower()

    assert "operação do dia" in text
    assert "clientes:" in text
    assert "financeiro:" in text
    assert "risco e caixa" in text
    assert "cobrança e-mail" in text
    assert "ciclo de contratos" in text
