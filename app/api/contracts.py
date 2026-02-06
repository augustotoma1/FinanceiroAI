"""
Contract Management API Endpoints

This module provides FastAPI endpoints for managing service contracts.
Supports CRUD operations for contracts with electronic signature integration
via Autentique platform and client relationship management.

Endpoints:
- POST / - Create a new contract
- GET / - List all contracts (with pagination and filtering)
- GET /{contract_id} - Get a specific contract by ID
- PUT /{contract_id} - Update an existing contract
- DELETE /{contract_id} - Delete a contract
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from app.database import get_db
from app.models.contract import Contract
from app.models.client import Client
from app.schemas.contract import ContractCreate, ContractUpdate, ContractResponse

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


@router.post("/", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(contract_data: ContractCreate, db: Session = Depends(get_db)):
    """
    Create a new contract.

    Creates a new contract record with the provided information. The contract_number
    must be unique in the system. If a contract with the same contract_number already
    exists, returns a 409 Conflict error. Also validates that the referenced client exists.

    Args:
        contract_data: Contract information (client_id, contract_number, service_description, etc.)
        db: Database session (injected)

    Returns:
        ContractResponse: Created contract with generated ID and timestamps

    Raises:
        HTTPException 404: If referenced client does not exist
        HTTPException 409: If contract_number already exists
        HTTPException 500: If database error occurs

    Example:
        POST /api/contracts/
        Body:
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

        Response (201):
        {
            "id": 1,
            "client_id": 1,
            "contract_number": "CTR-2024-001",
            ...
            "created_at": "2026-02-06T12:00:00Z",
            "updated_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        # Validate that the client exists
        client = db.query(Client).filter(Client.id == contract_data.client_id).first()
        if not client:
            logger.warning(f"Attempt to create contract for non-existent client ID: {contract_data.client_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client with ID {contract_data.client_id} not found"
            )

        # Check if contract with same contract_number already exists
        existing_contract = db.query(Contract).filter(
            Contract.contract_number == contract_data.contract_number
        ).first()

        if existing_contract:
            logger.warning(f"Attempt to create duplicate contract with number: {contract_data.contract_number}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Contract with number {contract_data.contract_number} already exists"
            )

        # Create new contract instance
        new_contract = Contract(**contract_data.model_dump())

        # Add to database
        db.add(new_contract)
        db.commit()
        db.refresh(new_contract)

        logger.info(f"Created new contract: {new_contract.id} - {new_contract.contract_number}")

        return new_contract

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error creating contract: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create contract"
        )


@router.get("/", response_model=List[ContractResponse], status_code=status.HTTP_200_OK)
async def list_contracts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search by contract number or service description"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    status_filter: Optional[str] = Query(None, description="Filter by contract status"),
    db: Session = Depends(get_db)
):
    """
    List all contracts with pagination and optional filtering.

    Returns a paginated list of contracts. Supports searching by contract number
    or service description, and filtering by client ID or status.

    Args:
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return (1-1000)
        search: Optional search term to filter by contract number or service description
        client_id: Optional filter by specific client ID
        status_filter: Optional filter by contract status (draft, pending_signature, signed, active, expired, cancelled)
        db: Database session (injected)

    Returns:
        List[ContractResponse]: List of contracts matching criteria

    Example:
        GET /api/contracts/?skip=0&limit=50
        Response (200):
        [
            {
                "id": 1,
                "client_id": 1,
                "contract_number": "CTR-2024-001",
                ...
            },
            {
                "id": 2,
                "client_id": 2,
                "contract_number": "CTR-2024-002",
                ...
            }
        ]

        GET /api/contracts/?client_id=1&status_filter=active
        Returns active contracts for client ID 1
    """
    try:
        # Build base query
        query = db.query(Contract)

        # Apply client_id filter if provided
        if client_id:
            query = query.filter(Contract.client_id == client_id)

        # Apply status filter if provided
        if status_filter:
            query = query.filter(Contract.status == status_filter)

        # Apply search filter if provided
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Contract.contract_number.ilike(search_pattern)) |
                (Contract.service_description.ilike(search_pattern))
            )

        # Apply pagination and ordering
        contracts = query.order_by(Contract.created_at.desc()).offset(skip).limit(limit).all()

        logger.info(f"Retrieved {len(contracts)} contracts (skip={skip}, limit={limit}, search={search}, client_id={client_id}, status={status_filter})")

        return contracts

    except Exception as e:
        logger.error(f"Error listing contracts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contracts"
        )


@router.get("/{contract_id}", response_model=ContractResponse, status_code=status.HTTP_200_OK)
async def get_contract(contract_id: int, db: Session = Depends(get_db)):
    """
    Get a specific contract by ID.

    Retrieves detailed information for a single contract identified by their
    unique ID.

    Args:
        contract_id: Contract primary key ID
        db: Database session (injected)

    Returns:
        ContractResponse: Contract data with all fields

    Raises:
        HTTPException 404: If contract not found

    Example:
        GET /api/contracts/1
        Response (200):
        {
            "id": 1,
            "client_id": 1,
            "contract_number": "CTR-2024-001",
            "service_description": "Website development services",
            "contract_value": 15000.00,
            ...
        }
    """
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()

        if not contract:
            logger.warning(f"Contract not found: {contract_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract with ID {contract_id} not found"
            )

        logger.info(f"Retrieved contract: {contract_id} - {contract.contract_number}")

        return contract

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error retrieving contract {contract_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve contract"
        )


@router.put("/{contract_id}", response_model=ContractResponse, status_code=status.HTTP_200_OK)
async def update_contract(
    contract_id: int,
    contract_data: ContractUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing contract.

    Updates contract information. Only provided fields will be updated.
    If updating contract_number, validates that the new number is not already in use.
    If updating client_id, validates that the new client exists.

    Args:
        contract_id: Contract primary key ID
        contract_data: Fields to update (all optional)
        db: Database session (injected)

    Returns:
        ContractResponse: Updated contract data

    Raises:
        HTTPException 404: If contract or referenced client not found
        HTTPException 409: If contract_number already exists (when updating contract_number)
        HTTPException 500: If database error occurs

    Example:
        PUT /api/contracts/1
        Body:
        {
            "status": "signed",
            "autentique_document_id": "doc-123456"
        }

        Response (200):
        {
            "id": 1,
            "status": "signed",
            "autentique_document_id": "doc-123456",
            ...
        }
    """
    try:
        # Get existing contract
        contract = db.query(Contract).filter(Contract.id == contract_id).first()

        if not contract:
            logger.warning(f"Attempt to update non-existent contract: {contract_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract with ID {contract_id} not found"
            )

        # Get update data, excluding unset fields
        update_data = contract_data.model_dump(exclude_unset=True)

        # If updating client_id, validate that the client exists
        if "client_id" in update_data:
            client = db.query(Client).filter(Client.id == update_data["client_id"]).first()
            if not client:
                logger.warning(f"Attempt to update contract with non-existent client ID: {update_data['client_id']}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Client with ID {update_data['client_id']} not found"
                )

        # If updating contract_number, check for duplicates
        if "contract_number" in update_data:
            existing_contract = db.query(Contract).filter(
                Contract.contract_number == update_data["contract_number"],
                Contract.id != contract_id
            ).first()

            if existing_contract:
                logger.warning(f"Attempt to update contract with duplicate number: {update_data['contract_number']}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Contract with number {update_data['contract_number']} already exists"
                )

        # Apply updates
        for field, value in update_data.items():
            setattr(contract, field, value)

        # Commit changes
        db.commit()
        db.refresh(contract)

        logger.info(f"Updated contract: {contract_id} - {contract.contract_number}")

        return contract

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error updating contract {contract_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update contract"
        )


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(contract_id: int, db: Session = Depends(get_db)):
    """
    Delete a contract.

    Permanently deletes a contract from the database. This operation cannot be undone.
    Use with caution. Consider updating the status to 'cancelled' instead for
    maintaining historical records.

    Args:
        contract_id: Contract primary key ID
        db: Database session (injected)

    Returns:
        None (204 No Content on success)

    Raises:
        HTTPException 404: If contract not found
        HTTPException 500: If database error occurs

    Example:
        DELETE /api/contracts/1
        Response (204): No content
    """
    try:
        contract = db.query(Contract).filter(Contract.id == contract_id).first()

        if not contract:
            logger.warning(f"Attempt to delete non-existent contract: {contract_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract with ID {contract_id} not found"
            )

        # Store contract info for logging before deletion
        contract_number = contract.contract_number

        # Delete contract
        db.delete(contract)
        db.commit()

        logger.info(f"Deleted contract: {contract_id} - {contract_number}")

        return None

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error deleting contract {contract_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete contract"
        )
