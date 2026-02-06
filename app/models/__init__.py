"""
Database Models Package

This package contains all SQLAlchemy ORM models for the financial automation system.
All models inherit from the Base class defined in app.database.

Models:
    - Client: Customer/client data model with Brazilian tax identification
    - Contract: Service contract model with financial terms and signature tracking
    - FinancialRecord: Financial transaction records (to be implemented)
    - Signature: Electronic signature tracking (to be implemented)
    - IntegrationToken: OAuth token storage for external services (to be implemented)
"""

from app.models.client import Client
from app.models.contract import Contract

__all__ = [
    "Client",
    "Contract",
]
