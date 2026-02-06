"""
Client Pydantic Schemas

This module defines Pydantic schemas for Client data validation and serialization.
Used for request validation and response formatting in the API layer.

Schemas:
    - ClientBase: Base schema with common fields
    - ClientCreate: Schema for creating new clients (POST requests)
    - ClientUpdate: Schema for updating existing clients (PUT/PATCH requests)
    - ClientResponse: Schema for API responses with full client data

All schemas support Brazilian client data including CPF/CNPJ tax identification
and Conta Azul platform integration.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, EmailStr


class ClientBase(BaseModel):
    """
    Base Client schema with common fields.

    This schema contains fields that are shared across create, update,
    and response schemas. It defines the core client information without
    database-specific fields like id and timestamps.

    Attributes:
        name: Full name or company name (required)
        email: Contact email address (optional, validated)
        phone: Contact phone number (optional)
        cpf_cnpj: Brazilian tax ID - CPF (11 digits) or CNPJ (14 digits)
        address_street: Street address (optional)
        address_city: City name (optional)
        address_state: State abbreviation (2 letters, e.g., "SP", "RJ")
        address_zip: ZIP/postal code (CEP in Brazil, format: 12345-678)
        conta_azul_id: External ID from Conta Azul platform (optional)
        notes: Additional notes or observations (optional)
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Full name or company name"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Contact email address"
    )
    phone: Optional[str] = Field(
        None,
        max_length=20,
        description="Contact phone number"
    )
    cpf_cnpj: str = Field(
        ...,
        min_length=11,
        max_length=20,
        description="Brazilian tax ID - CPF (11 digits) or CNPJ (14 digits)"
    )
    address_street: Optional[str] = Field(
        None,
        max_length=255,
        description="Street address"
    )
    address_city: Optional[str] = Field(
        None,
        max_length=100,
        description="City name"
    )
    address_state: Optional[str] = Field(
        None,
        min_length=2,
        max_length=2,
        description="State abbreviation (e.g., SP, RJ)"
    )
    address_zip: Optional[str] = Field(
        None,
        max_length=10,
        description="ZIP/postal code (CEP)"
    )
    conta_azul_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Conta Azul platform"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes or observations"
    )


class ClientCreate(ClientBase):
    """
    Schema for creating a new client.

    Used for POST /api/clients/ requests. Includes all fields from ClientBase.
    Does not include database-generated fields (id, timestamps).

    Example:
        {
            "name": "João Silva",
            "email": "joao@example.com",
            "phone": "+55 11 98765-4321",
            "cpf_cnpj": "12345678901",
            "address_street": "Rua Exemplo, 123",
            "address_city": "São Paulo",
            "address_state": "SP",
            "address_zip": "01234-567"
        }
    """
    pass


class ClientUpdate(BaseModel):
    """
    Schema for updating an existing client.

    Used for PUT/PATCH /api/clients/{id} requests. All fields are optional,
    allowing partial updates. Only provided fields will be updated.

    Example (partial update):
        {
            "email": "new.email@example.com",
            "phone": "+55 11 99999-8888"
        }
    """
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Full name or company name"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Contact email address"
    )
    phone: Optional[str] = Field(
        None,
        max_length=20,
        description="Contact phone number"
    )
    cpf_cnpj: Optional[str] = Field(
        None,
        min_length=11,
        max_length=20,
        description="Brazilian tax ID - CPF or CNPJ"
    )
    address_street: Optional[str] = Field(
        None,
        max_length=255,
        description="Street address"
    )
    address_city: Optional[str] = Field(
        None,
        max_length=100,
        description="City name"
    )
    address_state: Optional[str] = Field(
        None,
        min_length=2,
        max_length=2,
        description="State abbreviation"
    )
    address_zip: Optional[str] = Field(
        None,
        max_length=10,
        description="ZIP/postal code"
    )
    conta_azul_id: Optional[str] = Field(
        None,
        max_length=100,
        description="External ID from Conta Azul"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes"
    )


class ClientResponse(ClientBase):
    """
    Schema for client API responses.

    Used for GET /api/clients/ and GET /api/clients/{id} responses.
    Includes all fields from ClientBase plus database-generated fields
    (id, timestamps).

    The ConfigDict with from_attributes=True enables ORM mode, allowing
    this schema to serialize SQLAlchemy model instances directly.

    Attributes:
        id: Client primary key
        created_at: Timestamp when client was created
        updated_at: Timestamp when client was last updated
        last_synced_at: Timestamp of last sync with Conta Azul (optional)

    Example Response:
        {
            "id": 1,
            "name": "João Silva",
            "email": "joao@example.com",
            "phone": "+55 11 98765-4321",
            "cpf_cnpj": "12345678901",
            "address_street": "Rua Exemplo, 123",
            "address_city": "São Paulo",
            "address_state": "SP",
            "address_zip": "01234-567",
            "conta_azul_id": "ca_123456",
            "notes": null,
            "created_at": "2024-02-06T10:30:00Z",
            "updated_at": "2024-02-06T10:30:00Z",
            "last_synced_at": null
        }
    """
    id: int = Field(
        ...,
        description="Client primary key"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when client was created"
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when client was last updated"
    )
    last_synced_at: Optional[datetime] = Field(
        None,
        description="Timestamp of last sync with Conta Azul"
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "João Silva",
                "email": "joao@example.com",
                "phone": "+55 11 98765-4321",
                "cpf_cnpj": "12345678901",
                "address_street": "Rua Exemplo, 123",
                "address_city": "São Paulo",
                "address_state": "SP",
                "address_zip": "01234-567",
                "conta_azul_id": "ca_123456",
                "notes": None,
                "created_at": "2024-02-06T10:30:00Z",
                "updated_at": "2024-02-06T10:30:00Z",
                "last_synced_at": None
            }
        }
    )
