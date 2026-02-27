"""
Contract Pydantic Schemas

This module defines Pydantic schemas for Contract data validation and serialization.
Used for request validation and response formatting in the API layer.

Schemas:
    - ContractBase: Base schema with common fields
    - ContractCreate: Schema for creating new contracts (POST requests)
    - ContractUpdate: Schema for updating existing contracts (PUT/PATCH requests)
    - ContractResponse: Schema for API responses with full contract data

All schemas support Brazilian contract data including service agreements,
payment terms, and integration with Autentique for electronic signatures.
"""

from datetime import datetime, date
from typing import List, Optional
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict, EmailStr, model_validator


class ContractBase(BaseModel):
    """
    Base Contract schema with common fields.

    This schema contains fields that are shared across create, update,
    and response schemas. It defines the core contract information without
    database-specific fields like id and timestamps.

    Attributes:
        client_id: Foreign key reference to the client
        contract_number: Unique contract identifier (e.g., "CTR-2024-001")
        service_description: Detailed description of services to be provided
        contract_value: Total contract value in BRL (Brazilian Real)
        payment_terms: Payment schedule and terms description
        start_date: Contract start date
        end_date: Contract end date (optional for open-ended contracts)
        duration_months: Contract duration in months (optional)
        status: Contract status - draft, pending_signature, signed, active, expired, cancelled
        pdf_url: Path or URL to generated contract PDF document
        pdf_filename: Original filename of generated PDF
        conversation_id: ID of Claude conversation that generated this contract
        autentique_document_id: External ID from Autentique platform for signature tracking
        notes: Additional notes or special clauses
    """
    client_id: int = Field(
        ...,
        gt=0,
        description="Foreign key reference to the client"
    )
    contract_number: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique contract identifier (e.g., CTR-2024-001)"
    )
    service_description: str = Field(
        ...,
        min_length=1,
        description="Detailed description of services to be provided"
    )
    contract_value: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Total contract value in BRL (Brazilian Real)"
    )
    payment_terms: str = Field(
        ...,
        min_length=1,
        description="Payment schedule and terms description"
    )
    start_date: date = Field(
        ...,
        description="Contract start date"
    )
    end_date: Optional[date] = Field(
        None,
        description="Contract end date (optional for open-ended contracts)"
    )
    duration_months: Optional[int] = Field(
        None,
        gt=0,
        description="Contract duration in months"
    )
    status: str = Field(
        default="draft",
        max_length=50,
        description="Contract status: draft, pending_signature, signed, active, expired, cancelled"
    )
    pdf_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Path or URL to generated contract PDF document"
    )
    pdf_filename: Optional[str] = Field(
        None,
        max_length=255,
        description="Original filename of generated PDF"
    )
    conversation_id: Optional[str] = Field(
        None,
        max_length=100,
        description="ID of Claude conversation that generated this contract"
    )
    autentique_document_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Autentique platform for signature tracking"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes or special clauses"
    )


class ContractCreate(ContractBase):
    """
    Schema for creating a new contract.

    Used for POST /api/contracts/ requests. Includes all fields from ContractBase.
    Does not include database-generated fields (id, timestamps).

    Example:
        {
            "client_id": 1,
            "contract_number": "CTR-2024-001",
            "service_description": "Website development services",
            "contract_value": 15000.00,
            "payment_terms": "50% upfront, 50% on delivery",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "duration_months": 12,
            "status": "draft"
        }
    """
    pass


class ContractUpdate(BaseModel):
    """
    Schema for updating an existing contract.

    Used for PUT/PATCH /api/contracts/{id} requests. All fields are optional,
    allowing partial updates. Only provided fields will be updated.

    Example (partial update):
        {
            "status": "signed",
            "autentique_document_id": "doc-123456"
        }
    """
    client_id: Optional[int] = Field(
        None,
        gt=0,
        description="Foreign key reference to the client"
    )
    contract_number: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Unique contract identifier"
    )
    service_description: Optional[str] = Field(
        None,
        min_length=1,
        description="Detailed description of services"
    )
    contract_value: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2,
        description="Total contract value in BRL"
    )
    payment_terms: Optional[str] = Field(
        None,
        min_length=1,
        description="Payment schedule and terms"
    )
    start_date: Optional[date] = Field(
        None,
        description="Contract start date"
    )
    end_date: Optional[date] = Field(
        None,
        description="Contract end date"
    )
    duration_months: Optional[int] = Field(
        None,
        gt=0,
        description="Contract duration in months"
    )
    status: Optional[str] = Field(
        None,
        max_length=50,
        description="Contract status"
    )
    pdf_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Path or URL to PDF document"
    )
    pdf_filename: Optional[str] = Field(
        None,
        max_length=255,
        description="Original filename of PDF"
    )
    conversation_id: Optional[str] = Field(
        None,
        max_length=100,
        description="ID of Claude conversation"
    )
    autentique_document_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Autentique"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes"
    )


class ContractResponse(ContractBase):
    """
    Schema for contract API responses.

    Used for GET /api/contracts/ and GET /api/contracts/{id} responses.
    Includes all fields from ContractBase plus database-generated fields
    (id, timestamps).

    The ConfigDict with from_attributes=True enables ORM mode, allowing
    this schema to serialize SQLAlchemy model instances directly.

    Attributes:
        id: Contract primary key
        created_at: Timestamp when contract was created
        updated_at: Timestamp when contract was last updated
        signed_at: Timestamp when contract was signed by all parties (optional)

    Example response:
        {
            "id": 1,
            "client_id": 1,
            "contract_number": "CTR-2024-001",
            "service_description": "Website development services",
            "contract_value": 15000.00,
            "payment_terms": "50% upfront, 50% on delivery",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "duration_months": 12,
            "status": "signed",
            "pdf_url": "/contracts/CTR-2024-001.pdf",
            "pdf_filename": "CTR-2024-001.pdf",
            "conversation_id": "conv-abc123",
            "autentique_document_id": "doc-123456",
            "notes": null,
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-15T14:30:00Z",
            "signed_at": "2024-01-15T14:30:00Z"
        }
    """
    id: int = Field(
        ...,
        description="Contract primary key"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when contract was created"
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when contract was last updated"
    )
    signed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when contract was signed by all parties"
    )

    model_config = ConfigDict(from_attributes=True)


class ContractSignatureSignerRequest(BaseModel):
    """Signer payload for dispatching a contract to electronic signature."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Signer full name",
    )
    email: EmailStr = Field(
        ...,
        description="Signer email address",
    )
    cpf: Optional[str] = Field(
        None,
        max_length=20,
        description="Signer CPF/CNPJ (optional)",
    )
    action: str = Field(
        default="SIGN",
        min_length=1,
        max_length=20,
        description="Autentique signer action",
    )


class ContractSendForSignatureRequest(BaseModel):
    """Request body for sending a contract to Autentique."""

    template_name: str = Field(
        default="default_contract.html",
        min_length=1,
        max_length=255,
        description="Jinja2 template filename used to build the PDF",
    )
    show_audit_page: bool = Field(
        default=True,
        description="Include audit page on the generated Autentique document",
    )
    signers: Optional[List[ContractSignatureSignerRequest]] = Field(
        default=None,
        description="Optional signer list (defaults to contract client)",
    )

    @model_validator(mode="after")
    def _validate_non_empty_signers(self):
        if self.signers is not None and len(self.signers) == 0:
            raise ValueError("signers must contain at least one signer when provided")
        return self


class ContractSignatureSignerResult(BaseModel):
    """Signer row persisted locally after dispatch."""

    signer_name: str = Field(..., description="Signer name")
    signer_email: str = Field(..., description="Signer email")
    status: str = Field(..., description="Current local signature status")
    autentique_signature_id: Optional[str] = Field(
        None,
        description="Autentique signature public_id",
    )
    signature_token: Optional[str] = Field(
        None,
        description="Autentique signature short link/token",
    )


class ContractSendForSignatureResponse(BaseModel):
    """Response payload after dispatching contract for signature."""

    contract_id: int = Field(..., description="Contract ID")
    contract_number: str = Field(..., description="Contract number")
    status: str = Field(..., description="Updated contract status")
    autentique_document_id: str = Field(..., description="Autentique document ID")
    template_name: str = Field(..., description="Template used for PDF generation")
    signers_created: int = Field(..., ge=0, description="Number of new signature rows")
    signers_updated: int = Field(..., ge=0, description="Number of updated signature rows")
    signatures: List[ContractSignatureSignerResult] = Field(
        default_factory=list,
        description="Local signatures linked to the dispatched document",
    )
