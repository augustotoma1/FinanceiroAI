"""
Signature Database Model

This module defines the Signature model for tracking electronic signature status.
Each signature record represents one signer's interaction with a contract document
through the Autentique electronic signature platform.

The model tracks signer information, signature status, and audit trail data
for legal compliance and signature workflow monitoring.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Signature(Base):
    """
    Signature model for electronic signature tracking.

    Stores information about individual signers and their signature status
    for contracts sent through the Autentique platform. Each contract may
    have multiple signature records (one per signer).

    Attributes:
        id: Primary key, auto-incrementing integer
        contract_id: Foreign key to Contract table (required)
        signer_name: Full name of the person who should sign
        signer_email: Email address where signature request is sent
        signer_cpf: Brazilian CPF for legal identification (optional)
        status: Signature status - pending, signed, declined, expired
        autentique_signature_id: External signature ID from Autentique (public_id)
        signature_token: Unique token for signature link access
        signed_at: Timestamp when signature was completed
        declined_at: Timestamp when signature was declined (if applicable)
        ip_address: IP address from which signature was made (audit trail)
        user_agent: Browser user agent from signature session (audit trail)
        signature_method: Method used - email, sms, etc.
        notes: Additional notes or observations
        created_at: Timestamp when record was created (auto-generated)
        updated_at: Timestamp when record was last updated (auto-updated)

    Relationships:
        contract: Many-to-one relationship with Contract model

    Indexes:
        - contract_id: For contract-based queries
        - signer_email: For signer lookups
        - status: For status-based filtering
        - autentique_signature_id: For Autentique sync (unique constraint)

    Usage:
        # Create a new signature record
        signature = Signature(
            contract_id=1,
            signer_name="João Silva",
            signer_email="joao@example.com",
            signer_cpf="12345678901",
            status="pending"
        )
        db.add(signature)
        db.commit()

        # Query signatures
        pending_sigs = db.query(Signature).filter_by(status="pending").all()
        contract_sigs = db.query(Signature).filter_by(contract_id=1).all()
    """
    __tablename__ = "signatures"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Foreign key to Contract
    contract_id = Column(
        Integer,
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to contract that requires this signature"
    )

    # Signer information
    signer_name = Column(
        String(255),
        nullable=False,
        comment="Full name of the person who should sign"
    )
    signer_email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address where signature request is sent"
    )
    signer_cpf = Column(
        String(20),
        nullable=True,
        comment="Brazilian CPF for legal identification (11 digits)"
    )

    # Signature status tracking
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Signature status: pending, signed, declined, expired"
    )

    # Integration with Autentique
    autentique_signature_id = Column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="External signature ID from Autentique platform (public_id)"
    )
    signature_token = Column(
        String(255),
        nullable=True,
        comment="Unique token for signature link access"
    )

    # Signature completion tracking
    signed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when signature was completed"
    )
    declined_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when signature was declined (if applicable)"
    )

    # Audit trail
    ip_address = Column(
        String(45),
        nullable=True,
        comment="IP address from which signature was made (supports IPv6)"
    )
    user_agent = Column(
        String(500),
        nullable=True,
        comment="Browser user agent from signature session"
    )

    # Signature method
    signature_method = Column(
        String(50),
        nullable=True,
        default="email",
        comment="Method used for signature request: email, sms, etc."
    )

    # Additional information
    notes = Column(
        Text,
        nullable=True,
        comment="Additional notes or observations"
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

    # Relationships
    contract = relationship("Contract", backref="signatures")

    def __repr__(self) -> str:
        """String representation of Signature instance for debugging."""
        return f"<Signature(id={self.id}, signer_email='{self.signer_email}', status='{self.status}')>"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.signer_name} ({self.signer_email}) - {self.status}"
