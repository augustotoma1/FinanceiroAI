"""
Client Management API Endpoints

This module provides FastAPI endpoints for managing client data (customers/companies).
Supports CRUD operations for Brazilian clients with CPF/CNPJ identification
and Conta Azul platform integration.

Endpoints:
- POST / - Create a new client
- GET / - List all clients (with pagination)
- GET /{client_id} - Get a specific client by ID
- PUT /{client_id} - Update an existing client
- DELETE /{client_id} - Delete a client
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from app.database import get_db
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(client_data: ClientCreate, db: Session = Depends(get_db)):
    """
    Create a new client.

    Creates a new client record with the provided information. The CPF/CNPJ
    must be unique in the system. If a client with the same CPF/CNPJ already
    exists, returns a 409 Conflict error.

    Args:
        client_data: Client information (name, email, cpf_cnpj, etc.)
        db: Database session (injected)

    Returns:
        ClientResponse: Created client with generated ID and timestamps

    Raises:
        HTTPException 409: If CPF/CNPJ already exists
        HTTPException 500: If database error occurs

    Example:
        POST /api/clients/
        Body:
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

        Response (201):
        {
            "id": 1,
            "name": "João Silva",
            "email": "joao@example.com",
            ...
            "created_at": "2026-02-06T12:00:00Z",
            "updated_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        # Check if client with same CPF/CNPJ already exists
        existing_client = db.query(Client).filter(
            Client.cpf_cnpj == client_data.cpf_cnpj
        ).first()

        if existing_client:
            logger.warning(f"Attempt to create duplicate client with CPF/CNPJ: {client_data.cpf_cnpj}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Client with CPF/CNPJ {client_data.cpf_cnpj} already exists"
            )

        # Create new client instance
        new_client = Client(**client_data.model_dump())

        # Add to database
        db.add(new_client)
        db.commit()
        db.refresh(new_client)

        logger.info(f"Created new client: {new_client.id} - {new_client.name}")

        return new_client

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error creating client: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client"
        )


@router.get("/", response_model=List[ClientResponse], status_code=status.HTTP_200_OK)
async def list_clients(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search by name, email, or CPF/CNPJ"),
    db: Session = Depends(get_db)
):
    """
    List all clients with pagination and optional search.

    Returns a paginated list of clients. Supports searching by name, email,
    or CPF/CNPJ using the search parameter.

    Args:
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return (1-1000)
        search: Optional search term to filter by name, email, or CPF/CNPJ
        db: Database session (injected)

    Returns:
        List[ClientResponse]: List of clients matching criteria

    Example:
        GET /api/clients/?skip=0&limit=50
        Response (200):
        [
            {
                "id": 1,
                "name": "João Silva",
                "email": "joao@example.com",
                ...
            },
            {
                "id": 2,
                "name": "Maria Santos",
                "email": "maria@example.com",
                ...
            }
        ]

        GET /api/clients/?search=João
        Returns clients matching "João" in name, email, or CPF/CNPJ
    """
    try:
        # Build base query
        query = db.query(Client)

        # Apply search filter if provided
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Client.name.ilike(search_pattern)) |
                (Client.email.ilike(search_pattern)) |
                (Client.cpf_cnpj.ilike(search_pattern))
            )

        # Apply pagination and ordering
        clients = query.order_by(Client.created_at.desc()).offset(skip).limit(limit).all()

        logger.info(f"Retrieved {len(clients)} clients (skip={skip}, limit={limit}, search={search})")

        return clients

    except Exception as e:
        logger.error(f"Error listing clients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clients"
        )


@router.get("/{client_id}", response_model=ClientResponse, status_code=status.HTTP_200_OK)
async def get_client(client_id: int, db: Session = Depends(get_db)):
    """
    Get a specific client by ID.

    Retrieves detailed information for a single client identified by their
    unique ID.

    Args:
        client_id: Client primary key ID
        db: Database session (injected)

    Returns:
        ClientResponse: Client data with all fields

    Raises:
        HTTPException 404: If client not found

    Example:
        GET /api/clients/1
        Response (200):
        {
            "id": 1,
            "name": "João Silva",
            "email": "joao@example.com",
            "phone": "+55 11 98765-4321",
            "cpf_cnpj": "12345678901",
            ...
        }
    """
    try:
        client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            logger.warning(f"Client not found: {client_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client with ID {client_id} not found"
            )

        logger.info(f"Retrieved client: {client_id}")

        return client

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving client {client_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve client"
        )


@router.put("/{client_id}", response_model=ClientResponse, status_code=status.HTTP_200_OK)
async def update_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing client.

    Updates client information with the provided fields. Only fields included
    in the request body will be updated (partial update supported).

    Args:
        client_id: Client primary key ID
        client_data: Fields to update (all optional)
        db: Database session (injected)

    Returns:
        ClientResponse: Updated client data

    Raises:
        HTTPException 404: If client not found
        HTTPException 409: If updating CPF/CNPJ to one that already exists
        HTTPException 500: If database error occurs

    Example:
        PUT /api/clients/1
        Body:
        {
            "email": "newemail@example.com",
            "phone": "+55 11 99999-8888"
        }

        Response (200):
        {
            "id": 1,
            "name": "João Silva",
            "email": "newemail@example.com",
            "phone": "+55 11 99999-8888",
            ...
            "updated_at": "2026-02-06T13:00:00Z"
        }
    """
    try:
        # Find existing client
        client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            logger.warning(f"Client not found for update: {client_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client with ID {client_id} not found"
            )

        # Get update data, excluding unset fields
        update_data = client_data.model_dump(exclude_unset=True)

        # If CPF/CNPJ is being updated, check for duplicates
        if "cpf_cnpj" in update_data:
            existing_client = db.query(Client).filter(
                Client.cpf_cnpj == update_data["cpf_cnpj"],
                Client.id != client_id
            ).first()

            if existing_client:
                logger.warning(f"Attempt to update client {client_id} with duplicate CPF/CNPJ: {update_data['cpf_cnpj']}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Client with CPF/CNPJ {update_data['cpf_cnpj']} already exists"
                )

        # Update client fields
        for field, value in update_data.items():
            setattr(client, field, value)

        # Commit changes
        db.commit()
        db.refresh(client)

        logger.info(f"Updated client: {client_id}")

        return client

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating client {client_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update client"
        )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(client_id: int, db: Session = Depends(get_db)):
    """
    Delete a client.

    Permanently removes a client from the database. This operation cannot
    be undone. Consider deactivating clients instead of deleting them if
    historical data needs to be preserved.

    Args:
        client_id: Client primary key ID
        db: Database session (injected)

    Returns:
        No content (204 status code)

    Raises:
        HTTPException 404: If client not found
        HTTPException 500: If database error occurs

    Example:
        DELETE /api/clients/1
        Response: 204 No Content
    """
    try:
        client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            logger.warning(f"Client not found for deletion: {client_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client with ID {client_id} not found"
            )

        # Delete client
        db.delete(client)
        db.commit()

        logger.info(f"Deleted client: {client_id}")

        # Return no content (FastAPI automatically returns 204)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting client {client_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete client"
        )
