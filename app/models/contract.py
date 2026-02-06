"""
Contract Database Model

This module defines the Contract model for storing service contracts.
Contracts are generated through conversational AI data collection and
link to clients for service agreements.

The model tracks contract details including financial terms, dates,
status, and integration with Autentique for electronic signatures.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, Date, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Contract(Base):
    """
    Contract model for service agreement storage.

    Stores complete contract information including client relationship,
    financial terms, service description, and signature tracking.
    Integrates with Autentique platform for electronic signature workflow.

    Attributes:
        id: Primary key, auto-incrementing integer
        client_id: Foreign key to Client table (required)
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
        created_at: Timestamp when record was created (auto-generated)
        updated_at: Timestamp when record was last updated (auto-updated)
        signed_at: Timestamp when contract was signed by all parties

    Relationships:
        client: Many-to-one relationship with Client model

    Indexes:
        - contract_number: For fast contract lookups (unique constraint)
        - client_id: For client-based queries
        - status: For status-based filtering
        - autentique_document_id: For signature tracking (unique constraint)

    Usage:
        # Create a new contract
        contract = Contract(
            client_id=1,
            contract_number="CTR-2024-001",
            service_description="Website development services",
            contract_value=15000.00,
            payment_terms="50% upfront, 50% on delivery",
            start_date=date(2024, 1, 1),
            status="draft"
        )
        db.add(contract)
        db.commit()

        # Query contracts
        contract = db.query(Contract).filter_by(contract_number="CTR-2024-001").first()
        active_contracts = db.query(Contract).filter_by(status="active").all()
    """
    __tablename__ = "contracts"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Foreign key to Client
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to client who owns this contract"
    )

    # Contract identification
    contract_number = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique contract identifier (e.g., CTR-2024-001)"
    )

    # Service details
    service_description = Column(
        Text,
        nullable=False,
        comment="Detailed description of services to be provided"
    )

    # Financial information
    contract_value = Column(
        Numeric(15, 2),
        nullable=False,
        comment="Total contract value in BRL (Brazilian Real)"
    )
    payment_terms = Column(
        Text,
        nullable=False,
        comment="Payment schedule and terms description"
    )

    # Contract dates
    start_date = Column(
        Date,
        nullable=False,
        comment="Contract start date"
    )
    end_date = Column(
        Date,
        nullable=True,
        comment="Contract end date (optional for open-ended contracts)"
    )
    duration_months = Column(
        Integer,
        nullable=True,
        comment="Contract duration in months (optional)"
    )

    # Status tracking
    status = Column(
        String(50),
        nullable=False,
        default="draft",
        index=True,
        comment="Contract status: draft, pending_signature, signed, active, expired, cancelled"
    )

    # Document storage
    pdf_url = Column(
        String(500),
        nullable=True,
        comment="Path or URL to generated contract PDF document"
    )
    pdf_filename = Column(
        String(255),
        nullable=True,
        comment="Original filename of generated PDF"
    )

    # Integration fields
    conversation_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="ID of Claude conversation that generated this contract"
    )
    autentique_document_id = Column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="External ID from Autentique platform for signature tracking"
    )

    # Additional information
    notes = Column(
        Text,
        nullable=True,
        comment="Additional notes or special clauses"
    )

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
    signed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when contract was signed by all parties"
    )

    # Relationships
    client = relationship("Client", backref="contracts")

    def __repr__(self) -> str:
        """String representation of Contract instance for debugging."""
        return f"<Contract(id={self.id}, contract_number='{self.contract_number}', status='{self.status}')>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"Contract {self.contract_number} - {self.status}"
