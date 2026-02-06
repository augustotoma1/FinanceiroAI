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
"""

from app.schemas.client import (
    ClientBase,
    ClientCreate,
    ClientUpdate,
    ClientResponse
)

__all__ = [
    # Client schemas
    "ClientBase",
    "ClientCreate",
    "ClientUpdate",
    "ClientResponse",
]
