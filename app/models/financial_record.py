"""
Financial Record Database Model

This module defines the FinancialRecord model for storing financial transaction data.
Tracks invoices, payments, and receivables imported from Conta Azul accounting platform
for delinquency analysis and financial monitoring.

The model includes transaction details, payment tracking, client relationships,
and synchronization fields for integration with external systems.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, Date, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class FinancialRecord(Base):
    """
    Financial record model for transaction data storage.

    Stores complete financial transaction information including invoices,
    payments, and receivables. Used for delinquency analysis and payment
    pattern tracking. Integrates with Conta Azul for data synchronization.

    Attributes:
        id: Primary key, auto-incrementing integer
        client_id: Foreign key to Client table (required)
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
        conta_azul_id: External ID from Conta Azul platform for sync (unique)
        payment_method: Payment method - credit_card, bank_transfer, cash, pix, boleto
        notes: Additional notes or observations about the transaction
        created_at: Timestamp when record was created (auto-generated)
        updated_at: Timestamp when record was last updated (auto-updated)
        last_synced_at: Timestamp of last sync with Conta Azul

    Relationships:
        client: Many-to-one relationship with Client model

    Indexes:
        - transaction_number: For fast transaction lookups (unique constraint)
        - client_id: For client-based queries
        - status: For status-based filtering
        - transaction_type: For type-based filtering
        - due_date: For overdue payment queries
        - conta_azul_id: For sync operations (unique constraint)

    Usage:
        # Create a new financial record
        record = FinancialRecord(
            client_id=1,
            transaction_type="invoice",
            transaction_number="INV-2024-001",
            description="Website development - January 2024",
            amount=5000.00,
            status="pending",
            transaction_date=date(2024, 1, 1),
            due_date=date(2024, 1, 30)
        )
        db.add(record)
        db.commit()

        # Query financial records
        record = db.query(FinancialRecord).filter_by(transaction_number="INV-2024-001").first()
        overdue = db.query(FinancialRecord).filter(
            FinancialRecord.status == "overdue",
            FinancialRecord.due_date < date.today()
        ).all()
    """
    __tablename__ = "financial_records"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Foreign key to Client
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to client associated with this transaction"
    )

    # Transaction identification
    transaction_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of transaction: invoice, payment, receivable, expense"
    )
    transaction_number = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique transaction identifier (e.g., INV-2024-001)"
    )

    # Transaction details
    description = Column(
        Text,
        nullable=False,
        comment="Description of the transaction"
    )
    amount = Column(
        Numeric(15, 2),
        nullable=False,
        comment="Transaction amount in BRL (Brazilian Real)"
    )
    currency = Column(
        String(3),
        nullable=False,
        default="BRL",
        comment="Currency code (default: BRL for Brazilian Real)"
    )

    # Status tracking
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Transaction status: pending, paid, overdue, cancelled"
    )

    # Date tracking
    transaction_date = Column(
        Date,
        nullable=False,
        comment="Date when transaction was created/issued"
    )
    due_date = Column(
        Date,
        nullable=True,
        index=True,
        comment="Payment due date (for invoices and receivables)"
    )
    payment_date = Column(
        Date,
        nullable=True,
        comment="Actual payment date (when status becomes paid)"
    )
    days_overdue = Column(
        Integer,
        nullable=True,
        default=0,
        comment="Calculated field - days past due date (0 if not overdue)"
    )

    # Integration with Conta Azul
    conta_azul_id = Column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="External ID from Conta Azul platform for sync"
    )

    # Payment information
    payment_method = Column(
        String(50),
        nullable=True,
        comment="Payment method: credit_card, bank_transfer, cash, pix, boleto"
    )

    # Additional information
    notes = Column(
        Text,
        nullable=True,
        comment="Additional notes or observations about the transaction"
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
    last_synced_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last synchronization with Conta Azul timestamp"
    )

    # Relationships
    client = relationship("Client", backref="financial_records")

    def __repr__(self) -> str:
        """String representation of FinancialRecord instance for debugging."""
        return f"<FinancialRecord(id={self.id}, transaction_number='{self.transaction_number}', amount={self.amount}, status='{self.status}')>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.transaction_type.upper()} {self.transaction_number} - {self.currency} {self.amount} ({self.status})"
