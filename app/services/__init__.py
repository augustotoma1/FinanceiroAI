"""
Services Module

This module contains service clients for external API integrations:
- claude_service: Claude API integration for conversational AI
- conta_azul_service: Conta Azul OAuth2 client for accounting platform integration
- autentique_service: Autentique GraphQL client for electronic signatures
- contract_generator: Contract generation logic with PDF creation
- delinquency_analyzer: Payment analysis and risk scoring engine
- contract_lifecycle_service: Contract expiration lifecycle monitoring
- signature_sync_service: Autentique signature reconciliation and status sync
- email_billing_service: Automated receivable reminder campaign by email
- whatsapp_billing_service: Automated receivable reminder campaign by WhatsApp
- telegram_bot: Telegram bot interface for the system
"""

from __future__ import annotations

# Services will be imported here as they are implemented
from .claude_service import ClaudeService
from .conta_azul_service import ContaAzulService
from .autentique_service import AutentiqueService
from .contract_generator import ContractGenerator
from .delinquency_analyzer import DelinquencyAnalyzer
from .contract_lifecycle_service import (
    build_contract_lifecycle_snapshot,
    mark_expired_contracts,
    resolve_contract_end_date,
)
from .signature_sync_service import (
    sync_signatures_from_autentique,
    sync_signatures_for_document,
)
from .contract_signature_service import (
    send_contract_for_signature,
    ContractSignatureError,
    ContractSignatureNotFoundError,
    ContractSignatureConflictError,
    ContractSignatureValidationError,
    ContractSignatureProviderError,
)

# Optional integrations:
# If these modules are absent in a partial deploy, package import must not crash.
try:
    from .email_billing_service import run_billing_email_campaign
except Exception:  # pragma: no cover - defensive in production packaging
    async def run_billing_email_campaign(*_args, **_kwargs):  # type: ignore[override]
        raise ModuleNotFoundError(
            "app.services.email_billing_service is not available in this deployment"
        )

try:
    from .whatsapp_billing_service import (
        run_whatsapp_billing_campaign,
        list_blocked_whatsapp_targets,
        clear_blocked_whatsapp_targets,
    )
except Exception:  # pragma: no cover - defensive in production packaging
    async def run_whatsapp_billing_campaign(*_args, **_kwargs):  # type: ignore[override]
        raise ModuleNotFoundError(
            "app.services.whatsapp_billing_service is not available in this deployment"
        )

    def list_blocked_whatsapp_targets(*_args, **_kwargs):  # type: ignore[override]
        return []

    def clear_blocked_whatsapp_targets(*_args, **_kwargs):  # type: ignore[override]
        return 0
