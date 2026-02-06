"""
Client Database Model

This module defines the Client model for storing customer/client data.
Supports both individual clients (CPF) and corporate clients (CNPJ).
Integrates with Conta Azul accounting platform via conta_azul_id field.

The model includes full contact information, Brazilian tax identification,
and tracking fields for synchronization with external systems.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class Client(Base):
    """
    Client model for customer data storage.

    Stores complete client information including Brazilian tax identification
    (CPF for individuals, CNPJ for companies), contact details, and address.

    Attributes:
        id: Primary key, auto-incrementing integer
        name: Full name or company name (required)
        email: Contact email address (optional)
        phone: Contact phone number (optional)
        cpf_cnpj: Brazilian tax identification - CPF (11 digits) or CNPJ (14 digits)
        address_street: Street address (optional)
        address_city: City name (optional)
        address_state: State abbreviation (2 letters, e.g., "SP", "RJ")
        address_zip: ZIP/postal code (CEP in Brazil, format: 12345-678)
        conta_azul_id: External ID from Conta Azul platform for sync (unique)
        notes: Additional notes or observations about the client
        created_at: Timestamp when record was created (auto-generated)
        updated_at: Timestamp when record was last updated (auto-updated)
        last_synced_at: Timestamp of last sync with Conta Azul

    Indexes:
        - email: For fast email lookups
        - cpf_cnpj: For fast tax ID lookups (unique constraint)
        - conta_azul_id: For sync operations (unique constraint)

    Usage:
        # Create a new client
        client = Client(
            name="João Silva",
            email="joao@example.com",
            cpf_cnpj="12345678901",
            phone="+55 11 98765-4321"
        )
        db.add(client)
        db.commit()

        # Query clients
        client = db.query(Client).filter_by(cpf_cnpj="12345678901").first()
    """
    __tablename__ = "clients"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Basic information
    name = Column(String(255), nullable=False, comment="Full name or company name")
    email = Column(String(255), nullable=True, index=True, comment="Contact email")
    phone = Column(String(20), nullable=True, comment="Contact phone number")

    # Brazilian tax identification (CPF for individuals, CNPJ for companies)
    # CPF: 11 digits, CNPJ: 14 digits
    cpf_cnpj = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Brazilian tax ID - CPF (individual) or CNPJ (company)"
    )

    # Address information
    address_street = Column(String(255), nullable=True, comment="Street address")
    address_city = Column(String(100), nullable=True, comment="City name")
    address_state = Column(String(2), nullable=True, comment="State abbreviation (e.g., SP, RJ)")
    address_zip = Column(String(10), nullable=True, comment="ZIP/postal code (CEP)")

    # Integration with Conta Azul
    conta_azul_id = Column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="External ID from Conta Azul platform"
    )

    # Additional information
    notes = Column(Text, nullable=True, comment="Additional notes or observations")

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update timestamp"
    )
    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last synchronization with Conta Azul timestamp"
    )

    def __repr__(self) -> str:
        """String representation of Client instance for debugging."""
        return f"<Client(id={self.id}, name='{self.name}', cpf_cnpj='{self.cpf_cnpj}')>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.name} ({self.cpf_cnpj})"
