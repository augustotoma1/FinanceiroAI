"""
Database Models Package

This package contains all SQLAlchemy ORM models for the financial automation system.
All models inherit from the Base class defined in app.database.

Models:
    - Client: Customer/client data model with Brazilian tax identification
    - Contract: Service contract model with financial terms and signature tracking
    - FinancialRecord: Financial transaction records for invoices, payments, and receivables
    - Signature: Electronic signature tracking for contract workflow
    - IntegrationToken: OAuth token storage for external services (Conta Azul, etc.)
    - OAuthState: One-time OAuth state tokens persisted for CSRF protection
    - CashRiskSnapshot: Daily CFO snapshot with cash risk and projection indicators
"""

from app.models.client import Client
from app.models.contract import Contract
from app.models.financial_record import FinancialRecord
from app.models.signature import Signature
from app.models.integration_token import IntegrationToken
from app.models.conversation import Conversation
from app.models.oauth_state import OAuthState
from app.models.cash_risk_snapshot import CashRiskSnapshot

__all__ = [
    "Client",
    "Contract",
    "FinancialRecord",
    "Signature",
    "IntegrationToken",
    "Conversation",
    "OAuthState",
    "CashRiskSnapshot",
]
