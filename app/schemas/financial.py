"""
Financial Record Pydantic Schemas

This module defines Pydantic schemas for Financial Record data validation and serialization.
Used for request validation and response formatting in the API layer.

Schemas:
    - FinancialRecordBase: Base schema with common fields
    - FinancialRecordCreate: Schema for creating new financial records (POST requests)
    - FinancialRecordUpdate: Schema for updating existing financial records (PUT/PATCH requests)
    - FinancialRecordResponse: Schema for API responses with full financial record data

All schemas support Brazilian financial data including transactions, payments, and receivables
imported from Conta Azul platform for delinquency analysis and financial monitoring.
"""

from datetime import datetime, date
from typing import Optional
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class FinancialRecordBase(BaseModel):
    """
    Base Financial Record schema with common fields.

    This schema contains fields that are shared across create, update,
    and response schemas. It defines the core financial record information without
    database-specific fields like id and timestamps.

    Attributes:
        client_id: Foreign key reference to the client
        transaction_type: Type of transaction - invoice, payment, receivable, expense
        transaction_number: Unique transaction identifier (e.g., "INV-2024-001")
        description: Description of the transaction
        amount: Transaction amount in BRL (Brazilian Real)
        currency: Currency code (default: BRL for Brazilian Real)
        status: Transaction status - pending, paid, overdue, cancelled
        transaction_date: Date when transaction was created/issued
        due_date: Payment due date (for invoices and receivables)
        payment_date: Actual payment date (when status becomes paid)
        days_overdue: Calculated field - days past due date (0 if not overdue)
        conta_azul_id: External ID from Conta Azul platform for sync
        payment_method: Payment method - credit_card, bank_transfer, cash, pix, boleto
        notes: Additional notes or observations about the transaction
    """
    client_id: int = Field(
        ...,
        gt=0,
        description="Foreign key reference to the client"
    )
    transaction_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Type of transaction: invoice, payment, receivable, expense"
    )
    transaction_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique transaction identifier (e.g., INV-2024-001)"
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Description of the transaction"
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Transaction amount in BRL (Brazilian Real)"
    )
    currency: str = Field(
        default="BRL",
        min_length=3,
        max_length=3,
        description="Currency code (default: BRL for Brazilian Real)"
    )
    status: str = Field(
        default="pending",
        max_length=50,
        description="Transaction status: pending, paid, overdue, cancelled"
    )
    transaction_date: date = Field(
        ...,
        description="Date when transaction was created/issued"
    )
    due_date: Optional[date] = Field(
        None,
        description="Payment due date (for invoices and receivables)"
    )
    payment_date: Optional[date] = Field(
        None,
        description="Actual payment date (when status becomes paid)"
    )
    days_overdue: Optional[int] = Field(
        None,
        ge=0,
        description="Calculated field - days past due date (0 if not overdue)"
    )
    conta_azul_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Conta Azul platform for sync"
    )
    payment_method: Optional[str] = Field(
        None,
        max_length=50,
        description="Payment method: credit_card, bank_transfer, cash, pix, boleto"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes or observations about the transaction"
    )


class FinancialRecordCreate(FinancialRecordBase):
    """
    Schema for creating a new financial record.

    Used for POST /api/financial/ requests. Includes all fields from FinancialRecordBase.
    Does not include database-generated fields (id, timestamps).

    Example:
        {
            "client_id": 1,
            "transaction_type": "invoice",
            "transaction_number": "INV-2024-001",
            "description": "Website development - January 2024",
            "amount": 5000.00,
            "currency": "BRL",
            "status": "pending",
            "transaction_date": "2024-01-01",
            "due_date": "2024-01-30"
        }
    """
    pass


class FinancialRecordUpdate(BaseModel):
    """
    Schema for updating an existing financial record.

    Used for PUT/PATCH /api/financial/{id} requests. All fields are optional,
    allowing partial updates. Only provided fields will be updated.

    Example (partial update):
        {
            "status": "paid",
            "payment_date": "2024-01-25",
            "payment_method": "pix"
        }
    """
    client_id: Optional[int] = Field(
        None,
        gt=0,
        description="Foreign key reference to the client"
    )
    transaction_type: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Type of transaction"
    )
    transaction_number: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Unique transaction identifier"
    )
    description: Optional[str] = Field(
        None,
        min_length=1,
        description="Description of the transaction"
    )
    amount: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2,
        description="Transaction amount in BRL"
    )
    currency: Optional[str] = Field(
        None,
        min_length=3,
        max_length=3,
        description="Currency code"
    )
    status: Optional[str] = Field(
        None,
        max_length=50,
        description="Transaction status"
    )
    transaction_date: Optional[date] = Field(
        None,
        description="Date when transaction was created/issued"
    )
    due_date: Optional[date] = Field(
        None,
        description="Payment due date"
    )
    payment_date: Optional[date] = Field(
        None,
        description="Actual payment date"
    )
    days_overdue: Optional[int] = Field(
        None,
        ge=0,
        description="Days past due date"
    )
    conta_azul_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Conta Azul"
    )
    payment_method: Optional[str] = Field(
        None,
        max_length=50,
        description="Payment method"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes"
    )


class FinancialRecordResponse(FinancialRecordBase):
    """
    Schema for financial record API responses.

    Used for GET /api/financial/ and GET /api/financial/{id} responses.
    Includes all fields from FinancialRecordBase plus database-generated fields
    (id, timestamps).

    The ConfigDict with from_attributes=True enables ORM mode, allowing
    this schema to serialize SQLAlchemy model instances directly.

    Attributes:
        id: Financial record primary key
        created_at: Timestamp when record was created
        updated_at: Timestamp when record was last updated
        last_synced_at: Timestamp of last sync with Conta Azul (optional)

    Example response:
        {
            "id": 1,
            "client_id": 1,
            "transaction_type": "invoice",
            "transaction_number": "INV-2024-001",
            "description": "Website development - January 2024",
            "amount": 5000.00,
            "currency": "BRL",
            "status": "paid",
            "transaction_date": "2024-01-01",
            "due_date": "2024-01-30",
            "payment_date": "2024-01-25",
            "days_overdue": 0,
            "conta_azul_id": "ca-123456",
            "payment_method": "pix",
            "notes": null,
            "created_at": "2024-01-01T10:00:00Z",
            "updated_at": "2024-01-25T14:30:00Z",
            "last_synced_at": "2024-01-25T14:30:00Z"
        }
    """
    id: int = Field(
        ...,
        description="Financial record primary key"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when record was created"
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when record was last updated"
    )
    last_synced_at: Optional[datetime] = Field(
        None,
        description="Timestamp of last sync with Conta Azul"
    )

    model_config = ConfigDict(from_attributes=True)
