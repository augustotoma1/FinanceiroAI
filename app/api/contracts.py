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

from fastapi import APIRouter, Body, HTTPException, status, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import io

from app.database import get_db
from app.models.contract import Contract
from app.models.client import Client
from app.schemas.contract import (
    ContractCreate,
    ContractUpdate,
    ContractResponse,
    ContractSendForSignatureRequest,
    ContractSendForSignatureResponse,
)
from app.services.contract_generator import (
    ContractGenerator,
    ContractValidationError,
    ContractTemplateError,
    ContractPDFError,
)
from app.services.contract_signature_service import (
    ContractSignatureConflictError,
    ContractSignatureError,
    ContractSignatureNotFoundError,
    ContractSignatureProviderError,
    ContractSignatureValidationError,
    send_contract_for_signature,
)

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


def _build_template_payload(contract: Contract, client: Client) -> dict:
    """Map contract + client DB models to contract template payload fields."""
    return {
        "client_name": client.name,
        "cpf_cnpj": client.cpf_cnpj,
        "service_description": contract.service_description,
        "contract_value": float(contract.contract_value),
        "payment_terms": contract.payment_terms,
        "start_date": contract.start_date.isoformat() if contract.start_date else None,
        "duration_months": contract.duration_months,
        "special_clauses": contract.notes or "",
    }


def _get_contract_and_client_or_404(db: Session, contract_id: int) -> tuple[Contract, Client]:
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contract with ID {contract_id} not found",
        )

    client = db.query(Client).filter(Client.id == contract.client_id).first()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {contract.client_id} not found for contract {contract_id}",
        )
    return contract, client


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

        # Apply status filter using explicit query contract.
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

        logger.info(
            "Retrieved %s contracts (skip=%s, limit=%s, search=%s, client_id=%s, status=%s)",
            len(contracts),
            skip,
            limit,
            search,
            client_id,
            status_filter,
        )

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


@router.get("/templates/available", status_code=status.HTTP_200_OK)
async def list_contract_templates():
    """
    List available Jinja2 contract templates for dynamic contract rendering.
    """
    generator = ContractGenerator()
    templates = generator.list_available_templates()
    return {
        "default_template": "default_contract.html",
        "templates": templates,
        "total": len(templates),
    }


@router.get(
    "/{contract_id}/preview",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
)
async def preview_contract_template(
    contract_id: int,
    template_name: str = Query("default_contract.html", description="Jinja2 template filename"),
    db: Session = Depends(get_db),
):
    """
    Render HTML preview of a contract using the selected template.
    """
    try:
        contract, client = _get_contract_and_client_or_404(db, contract_id)
        payload = _build_template_payload(contract, client)
        generator = ContractGenerator()
        html = await generator.generate_contract_html(
            contract_data=payload,
            contract_id=contract.contract_number,
            template_name=template_name,
        )
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except (ContractValidationError, ContractTemplateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error previewing contract template for contract %s: %s", contract_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to preview contract template",
        )


@router.get("/{contract_id}/pdf", status_code=status.HTTP_200_OK)
async def generate_contract_pdf(
    contract_id: int,
    template_name: str = Query("default_contract.html", description="Jinja2 template filename"),
    db: Session = Depends(get_db),
):
    """
    Generate contract PDF bytes using selected template (dynamic Jinja2 rendering).
    """
    try:
        contract, client = _get_contract_and_client_or_404(db, contract_id)
        payload = _build_template_payload(contract, client)
        generator = ContractGenerator()
        pdf_bytes = await generator.generate_contract_pdf(
            contract_data=payload,
            contract_id=contract.contract_number,
            template_name=template_name,
        )
        filename = f"{contract.contract_number}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except (ContractValidationError, ContractTemplateError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except ContractPDFError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error generating contract PDF for contract %s: %s", contract_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate contract PDF",
        )


@router.post(
    "/{contract_id}/send-for-signature",
    response_model=ContractSendForSignatureResponse,
    status_code=status.HTTP_200_OK,
)
async def send_contract_to_signature_provider(
    contract_id: int,
    request: ContractSendForSignatureRequest = Body(default_factory=ContractSendForSignatureRequest),
    db: Session = Depends(get_db),
):
    """
    Generate a contract PDF and send it to Autentique for signature.
    """
    try:
        payload = await send_contract_for_signature(
            db,
            contract_id=contract_id,
            template_name=request.template_name,
            signers=[signer.model_dump() for signer in request.signers] if request.signers else None,
            show_audit_page=request.show_audit_page,
        )
        return payload
    except ContractSignatureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ContractSignatureConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ContractSignatureValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ContractSignatureProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to dispatch contract to Autentique: {exc}",
        ) from exc
    except ContractSignatureError as exc:
        logger.error("Contract signature dispatch failed for contract %s: %s", contract_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch contract for signature",
        ) from exc
