"""
Signature Management API Endpoints

This module provides FastAPI endpoints for managing electronic signatures.
Supports CRUD operations for signature tracking with Autentique platform
integration and signature workflow management.

Endpoints:
- POST / - Create a new signature record
- GET / - List all signatures (with pagination and filtering)
- GET /{signature_id} - Get a specific signature by ID
- PUT /{signature_id} - Update an existing signature
- DELETE /{signature_id} - Delete a signature
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from datetime import datetime, timezone

from app.database import get_db
from app.models.signature import Signature
from app.models.contract import Contract
from app.schemas.signature import SignatureCreate, SignatureUpdate, SignatureResponse

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()

FINAL_CONTRACT_STATUSES = {"cancelled", "expired"}
SIGNED_SIGNATURE_STATUSES = {"signed"}


def _normalize_status(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _sync_contract_signature_status(db: Session, contract_id: int) -> None:
    """
    Align contract.status with the current set of signer statuses.

    Rules:
    - Any non-terminal contract with at least one non-signed signer => pending_signature
    - All signers signed => signed (or active when start_date is already effective)
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        return

    current_status = _normalize_status(contract.status)
    if current_status in FINAL_CONTRACT_STATUSES:
        return

    signatures = db.query(Signature).filter(Signature.contract_id == contract_id).all()
    if not signatures:
        return

    signature_statuses = [_normalize_status(sig.status) for sig in signatures]
    all_signed = all(status in SIGNED_SIGNATURE_STATUSES for status in signature_statuses)

    if all_signed:
        today = datetime.now(timezone.utc).date()
        target_status = "active" if contract.start_date and contract.start_date <= today else "signed"
        if current_status != target_status:
            contract.status = target_status
        if contract.signed_at is None:
            contract.signed_at = datetime.now(timezone.utc)
        return

    # If there is at least one signer not fully signed, keep workflow in signature phase.
    if current_status != "pending_signature":
        contract.status = "pending_signature"


@router.post("/", response_model=SignatureResponse, status_code=status.HTTP_201_CREATED)
async def create_signature(signature_data: SignatureCreate, db: Session = Depends(get_db)):
    """
    Create a new signature record.

    Creates a new signature record with the provided information. Validates that
    the referenced contract exists. Multiple signatures can be created for the same
    contract (one per signer).

    Args:
        signature_data: Signature information (contract_id, signer_name, signer_email, etc.)
        db: Database session (injected)

    Returns:
        SignatureResponse: Created signature with generated ID and timestamps

    Raises:
        HTTPException 404: If referenced contract does not exist
        HTTPException 500: If database error occurs

    Example:
        POST /api/signatures/
        Body:
        {
            "contract_id": 1,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "signer_cpf": "12345678901",
            "status": "pending",
            "signature_method": "email"
        }

        Response (201):
        {
            "id": 1,
            "contract_id": 1,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            ...
            "created_at": "2026-02-06T12:00:00Z",
            "updated_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        # Validate that the contract exists
        contract = db.query(Contract).filter(Contract.id == signature_data.contract_id).first()
        if not contract:
            logger.warning(f"Attempt to create signature for non-existent contract ID: {signature_data.contract_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract with ID {signature_data.contract_id} not found"
            )

        payload = signature_data.model_dump()
        if _normalize_status(payload.get("status")) == "signed" and not payload.get("signed_at"):
            payload["signed_at"] = datetime.now(timezone.utc)

        # Create new signature instance
        new_signature = Signature(**payload)

        # Add to database
        db.add(new_signature)
        db.flush()
        _sync_contract_signature_status(db, new_signature.contract_id)
        db.commit()
        db.refresh(new_signature)

        logger.info(f"Created new signature: {new_signature.id} - {new_signature.signer_email}")

        return new_signature

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error creating signature: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create signature"
        )


@router.get("/", response_model=List[SignatureResponse], status_code=status.HTTP_200_OK)
async def list_signatures(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search by signer name or email"),
    contract_id: Optional[int] = Query(None, description="Filter by contract ID"),
    status_filter: Optional[str] = Query(None, description="Filter by signature status"),
    db: Session = Depends(get_db)
):
    """
    List all signatures with pagination and optional filtering.

    Returns a paginated list of signatures. Supports searching by signer name
    or email, and filtering by contract ID or status.

    Args:
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return (1-1000)
        search: Optional search term to filter by signer name or email
        contract_id: Optional filter by specific contract ID
        status_filter: Optional filter by signature status (pending, signed, declined, expired)
        db: Database session (injected)

    Returns:
        List[SignatureResponse]: List of signatures matching criteria

    Example:
        GET /api/signatures/?skip=0&limit=50
        Response (200):
        [
            {
                "id": 1,
                "contract_id": 1,
                "signer_name": "João Silva",
                "signer_email": "joao@example.com",
                ...
            },
            {
                "id": 2,
                "contract_id": 2,
                "signer_name": "Maria Santos",
                "signer_email": "maria@example.com",
                ...
            }
        ]

        GET /api/signatures/?contract_id=1&status_filter=pending
        Returns pending signatures for contract ID 1
    """
    try:
        # Build base query
        query = db.query(Signature)

        # Apply contract_id filter if provided
        if contract_id:
            query = query.filter(Signature.contract_id == contract_id)

        # Apply status filter using explicit query contract.
        if status_filter:
            query = query.filter(Signature.status == status_filter)

        # Apply search filter if provided
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Signature.signer_name.ilike(search_pattern)) |
                (Signature.signer_email.ilike(search_pattern))
            )

        # Apply pagination and ordering
        signatures = query.order_by(Signature.created_at.desc()).offset(skip).limit(limit).all()

        logger.info(
            "Retrieved %s signatures (skip=%s, limit=%s, search=%s, contract_id=%s, status=%s)",
            len(signatures),
            skip,
            limit,
            search,
            contract_id,
            status_filter,
        )

        return signatures

    except Exception as e:
        logger.error(f"Error listing signatures: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve signatures"
        )


@router.get("/{signature_id}", response_model=SignatureResponse, status_code=status.HTTP_200_OK)
async def get_signature(signature_id: int, db: Session = Depends(get_db)):
    """
    Get a specific signature by ID.

    Retrieves detailed information for a single signature record.

    Args:
        signature_id: ID of the signature to retrieve
        db: Database session (injected)

    Returns:
        SignatureResponse: Signature details

    Raises:
        HTTPException 404: If signature with given ID does not exist
        HTTPException 500: If database error occurs

    Example:
        GET /api/signatures/1
        Response (200):
        {
            "id": 1,
            "contract_id": 1,
            "signer_name": "João Silva",
            "signer_email": "joao@example.com",
            "signer_cpf": "12345678901",
            "status": "signed",
            ...
        }
    """
    try:
        signature = db.query(Signature).filter(Signature.id == signature_id).first()

        if not signature:
            logger.warning(f"Signature not found: {signature_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signature with ID {signature_id} not found"
            )

        logger.info(f"Retrieved signature: {signature_id}")

        return signature

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error retrieving signature {signature_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve signature"
        )


@router.put("/{signature_id}", response_model=SignatureResponse, status_code=status.HTTP_200_OK)
async def update_signature(
    signature_id: int,
    signature_data: SignatureUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing signature.

    Updates signature information. All fields in the request body are optional.
    Only provided fields will be updated. If contract_id is being updated,
    validates that the new contract exists.

    Args:
        signature_id: ID of the signature to update
        signature_data: Updated signature fields (all optional)
        db: Database session (injected)

    Returns:
        SignatureResponse: Updated signature

    Raises:
        HTTPException 404: If signature or new contract does not exist
        HTTPException 500: If database error occurs

    Example:
        PUT /api/signatures/1
        Body:
        {
            "status": "signed",
            "signed_at": "2024-01-15T14:30:00Z",
            "ip_address": "192.168.1.1"
        }

        Response (200):
        {
            "id": 1,
            "contract_id": 1,
            "status": "signed",
            "signed_at": "2024-01-15T14:30:00Z",
            "ip_address": "192.168.1.1",
            ...
        }
    """
    try:
        # Get existing signature
        signature = db.query(Signature).filter(Signature.id == signature_id).first()

        if not signature:
            logger.warning(f"Signature not found for update: {signature_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signature with ID {signature_id} not found"
            )

        # If updating contract_id, validate that the new contract exists
        if signature_data.contract_id is not None and signature_data.contract_id != signature.contract_id:
            contract = db.query(Contract).filter(Contract.id == signature_data.contract_id).first()
            if not contract:
                logger.warning(f"Attempt to update signature to non-existent contract ID: {signature_data.contract_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Contract with ID {signature_data.contract_id} not found"
                )

        # Update signature fields
        original_contract_id = signature.contract_id
        update_data = signature_data.model_dump(exclude_unset=True)

        updated_status = _normalize_status(update_data.get("status"))
        if updated_status == "signed" and update_data.get("signed_at") is None:
            update_data["signed_at"] = datetime.now(timezone.utc)
        if updated_status in {"declined", "rejected"} and update_data.get("declined_at") is None:
            update_data["declined_at"] = datetime.now(timezone.utc)

        for field, value in update_data.items():
            setattr(signature, field, value)

        # Commit changes
        db.flush()
        affected_contract_ids = {original_contract_id, signature.contract_id}
        for contract_id in affected_contract_ids:
            _sync_contract_signature_status(db, int(contract_id))
        db.commit()
        db.refresh(signature)

        logger.info(f"Updated signature: {signature_id}")

        return signature

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error updating signature {signature_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update signature"
        )


@router.delete("/{signature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signature(signature_id: int, db: Session = Depends(get_db)):
    """
    Delete a signature record.

    Permanently deletes a signature from the database. This operation cannot be undone.
    Use with caution - consider updating the status to 'cancelled' instead for audit trail.

    Args:
        signature_id: ID of the signature to delete
        db: Database session (injected)

    Returns:
        None (204 No Content on success)

    Raises:
        HTTPException 404: If signature with given ID does not exist
        HTTPException 500: If database error occurs

    Example:
        DELETE /api/signatures/1
        Response (204):
        No content
    """
    try:
        signature = db.query(Signature).filter(Signature.id == signature_id).first()

        if not signature:
            logger.warning(f"Signature not found for deletion: {signature_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signature with ID {signature_id} not found"
            )

        # Delete signature
        contract_id = signature.contract_id
        db.delete(signature)
        db.flush()
        _sync_contract_signature_status(db, int(contract_id))
        db.commit()

        logger.info(f"Deleted signature: {signature_id}")

        return None

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error deleting signature {signature_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete signature"
        )
