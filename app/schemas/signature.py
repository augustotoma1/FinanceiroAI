"""
Signature Pydantic Schemas

This module defines Pydantic schemas for Signature data validation and serialization.
Used for request validation and response formatting in the API layer.

Schemas:
    - SignatureBase: Base schema with common fields
    - SignatureCreate: Schema for creating new signatures (POST requests)
    - SignatureUpdate: Schema for updating existing signatures (PUT/PATCH requests)
    - SignatureResponse: Schema for API responses with full signature data

All schemas support electronic signature workflow tracking with Autentique platform
integration and audit trail information.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr, ConfigDict


class SignatureBase(BaseModel):
    """
    Base Signature schema with common fields.

    This schema contains fields that are shared across create, update,
    and response schemas. It defines the core signature information without
    database-specific fields like id and timestamps.

    Attributes:
        contract_id: Foreign key reference to the contract
        signer_name: Full name of the person who should sign
        signer_email: Email address where signature request is sent
        signer_cpf: Brazilian CPF for legal identification (optional)
        status: Signature status - pending, signed, declined, expired
        autentique_signature_id: External signature ID from Autentique (public_id)
        signature_token: Unique token for signature link access
        signed_at: Timestamp when signature was completed
        declined_at: Timestamp when signature was declined
        ip_address: IP address from which signature was made
        user_agent: Browser user agent from signature session
        signature_method: Method used - email, sms, etc.
        notes: Additional notes or observations
    """
    contract_id: int = Field(
        ...,
        gt=0,
        description="Foreign key reference to the contract"
    )
    signer_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Full name of the person who should sign"
    )
    signer_email: EmailStr = Field(
        ...,
        description="Email address where signature request is sent"
    )
    signer_cpf: Optional[str] = Field(
        None,
        max_length=20,
        description="Brazilian CPF for legal identification (11 digits)"
    )
    status: str = Field(
        default="pending",
        max_length=50,
        description="Signature status: pending, signed, declined, expired"
    )
    autentique_signature_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External signature ID from Autentique platform (public_id)"
    )
    signature_token: Optional[str] = Field(
        None,
        max_length=255,
        description="Unique token for signature link access"
    )
    signed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when signature was completed"
    )
    declined_at: Optional[datetime] = Field(
        None,
        description="Timestamp when signature was declined"
    )
    ip_address: Optional[str] = Field(
        None,
        max_length=45,
        description="IP address from which signature was made (supports IPv6)"
    )
    user_agent: Optional[str] = Field(
        None,
        max_length=500,
        description="Browser user agent from signature session"
    )
    signature_method: Optional[str] = Field(
        "email",
        max_length=50,
        description="Method used for signature request: email, sms, etc."
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes or observations"
    )


class SignatureCreate(SignatureBase):
    """
    Schema for creating a new signature.

    Used for POST /api/signatures/ requests. Includes all fields from SignatureBase.
    Does not include database-generated fields (id, timestamps).

    Example:
        {
            "contract_id": 1,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "signer_cpf": "12345678901",
            "status": "pending",
            "signature_method": "email"
        }
    """
    pass


class SignatureUpdate(BaseModel):
    """
    Schema for updating an existing signature.

    Used for PUT/PATCH /api/signatures/{id} requests. All fields are optional,
    allowing partial updates. Only provided fields will be updated.

    Example (partial update):
        {
            "status": "signed",
            "signed_at": "2024-01-15T14:30:00Z",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0..."
        }
    """
    contract_id: Optional[int] = Field(
        None,
        gt=0,
        description="Foreign key reference to the contract"
    )
    signer_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Full name of the person who should sign"
    )
    signer_email: Optional[EmailStr] = Field(
        None,
        description="Email address where signature request is sent"
    )
    signer_cpf: Optional[str] = Field(
        None,
        max_length=20,
        description="Brazilian CPF for legal identification"
    )
    status: Optional[str] = Field(
        None,
        max_length=50,
        description="Signature status"
    )
    autentique_signature_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External signature ID from Autentique"
    )
    signature_token: Optional[str] = Field(
        None,
        max_length=255,
        description="Unique token for signature link access"
    )
    signed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when signature was completed"
    )
    declined_at: Optional[datetime] = Field(
        None,
        description="Timestamp when signature was declined"
    )
    ip_address: Optional[str] = Field(
        None,
        max_length=45,
        description="IP address from which signature was made"
    )
    user_agent: Optional[str] = Field(
        None,
        max_length=500,
        description="Browser user agent from signature session"
    )
    signature_method: Optional[str] = Field(
        None,
        max_length=50,
        description="Method used for signature request"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes"
    )


class SignatureResponse(SignatureBase):
    """
    Schema for signature API responses.

    Used for GET /api/signatures/ and GET /api/signatures/{id} responses.
    Includes all fields from SignatureBase plus database-generated fields
    (id, timestamps).

    The ConfigDict with from_attributes=True enables ORM mode, allowing
    this schema to serialize SQLAlchemy model instances directly.

    Attributes:
        id: Signature primary key
        created_at: Timestamp when signature record was created
        updated_at: Timestamp when signature record was last updated

    Example response:
        {
            "id": 1,
            "contract_id": 1,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "signer_cpf": "12345678901",
            "status": "signed",
            "autentique_signature_id": "sig-123456",
            "signature_token": "token-abc123",
            "signed_at": "2024-01-15T14:30:00Z",
            "declined_at": null,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0...",
            "signature_method": "email",
            "notes": null,
            "created_at": "2024-01-10T10:00:00Z",
            "updated_at": "2024-01-15T14:30:00Z"
        }
    """
    id: int = Field(
        ...,
        description="Signature primary key"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when signature record was created"
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when signature record was last updated"
    )

    model_config = ConfigDict(from_attributes=True)
