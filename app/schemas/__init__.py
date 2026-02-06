"""
Pydantic Schemas Package

This package contains all Pydantic schemas for request/response validation
and data serialization in the API layer.

Schemas are organized by domain model:
- client: Client data validation schemas
- contract: Contract data validation schemas
- financial: Financial record validation schemas

Usage:
    from app.schemas.client import ClientCreate, ClientResponse
    from app.schemas.contract import ContractCreate, ContractResponse
    from app.schemas.financial import FinancialRecordCreate, FinancialRecordResponse
"""

from app.schemas.client import (
    ClientBase,
    ClientCreate,
    ClientUpdate,
    ClientResponse
)
from app.schemas.contract import (
    ContractBase,
    ContractCreate,
    ContractUpdate,
    ContractResponse
)
from app.schemas.financial import (
    FinancialRecordBase,
    FinancialRecordCreate,
    FinancialRecordUpdate,
    FinancialRecordResponse
)

__all__ = [
    # Client schemas
    "ClientBase",
    "ClientCreate",
    "ClientUpdate",
    "ClientResponse",
    # Contract schemas
    "ContractBase",
    "ContractCreate",
    "ContractUpdate",
    "ContractResponse",
    # Financial schemas
    "FinancialRecordBase",
    "FinancialRecordCreate",
    "FinancialRecordUpdate",
    "FinancialRecordResponse",
]
