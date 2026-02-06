"""
Client Synchronization Background Job

This module provides a background job for synchronizing client data between
Conta Azul accounting platform and the local database. The job fetches all
customers from Conta Azul and creates or updates local Client records.

The synchronization uses CPF/CNPJ as the natural key to match clients and
implements an upsert pattern to avoid duplicates.

Usage:
    from app.background.sync_clients import sync_clients_job

    # Run synchronization manually
    await sync_clients_job()

    # Or schedule with APScheduler
    scheduler.add_job(sync_clients_job, 'interval', hours=1)
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.client import Client
from app.models.integration_token import IntegrationToken
from app.services.conta_azul_service import (
    ContaAzulService,
    ContaAzulError,
    ContaAzulAuthError
)

logger = logging.getLogger(__name__)


class ClientSyncError(Exception):
    """Base exception for client synchronization errors."""
    pass


class ClientSyncAuthError(ClientSyncError):
    """Exception raised when Conta Azul authentication fails."""
    pass


class ClientSyncDataError(ClientSyncError):
    """Exception raised when client data processing fails."""
    pass


async def sync_clients_job() -> Dict[str, Any]:
    """
    Background job to synchronize clients from Conta Azul to local database.

    This job performs the following steps:
    1. Retrieve valid Conta Azul OAuth token from database
    2. Fetch all customers from Conta Azul API
    3. For each customer, create new or update existing Client record
    4. Use CPF/CNPJ as natural key for matching
    5. Update last_synced_at timestamp on all synced records

    The job uses an upsert pattern (update if exists, create if not) to handle
    both new clients and updates to existing clients.

    Returns:
        Dict containing synchronization results:
            - success: bool indicating if sync completed successfully
            - synced_count: number of clients synced
            - created_count: number of new clients created
            - updated_count: number of existing clients updated
            - error_count: number of errors encountered
            - errors: list of error messages
            - duration_seconds: time taken to complete sync

    Raises:
        ClientSyncAuthError: If Conta Azul authentication fails
        ClientSyncError: If synchronization fails catastrophically

    Example:
        >>> result = await sync_clients_job()
        >>> print(f"Synced {result['synced_count']} clients")
        >>> if result['errors']:
        ...     print(f"Encountered {result['error_count']} errors")
    """
    start_time = datetime.utcnow()
    logger.info("Starting client synchronization job")

    db: Session = SessionLocal()
    synced_count = 0
    created_count = 0
    updated_count = 0
    error_count = 0
    errors: List[str] = []

    try:
        # Step 1: Get valid Conta Azul token
        logger.info("Retrieving Conta Azul OAuth token")
        access_token = await _get_valid_conta_azul_token(db)

        # Step 2: Fetch customers from Conta Azul
        logger.info("Fetching customers from Conta Azul API")
        conta_azul_service = ContaAzulService()
        customers = await conta_azul_service.get_customers(
            access_token=access_token,
            limit=1000  # Fetch up to 1000 customers per sync
        )

        logger.info(f"Retrieved {len(customers)} customers from Conta Azul")

        # Step 3: Process each customer
        for customer_data in customers:
            try:
                created, updated = await _sync_single_client(db, customer_data)
                synced_count += 1
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                error_msg = f"Failed to sync client {customer_data.get('id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue  # Continue with next customer

        # Step 4: Commit all changes
        db.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"Client synchronization completed successfully: "
            f"{synced_count} synced ({created_count} created, {updated_count} updated), "
            f"{error_count} errors in {duration:.2f}s"
        )

        return {
            "success": True,
            "synced_count": synced_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors,
            "duration_seconds": duration,
            "timestamp": datetime.utcnow().isoformat()
        }

    except ClientSyncAuthError as e:
        logger.error(f"Authentication error during client sync: {e}")
        db.rollback()
        raise

    except Exception as e:
        logger.error(f"Unexpected error during client sync: {e}", exc_info=True)
        db.rollback()
        raise ClientSyncError(f"Client synchronization failed: {e}")

    finally:
        db.close()


async def _get_valid_conta_azul_token(db: Session) -> str:
    """
    Retrieve a valid Conta Azul access token from the database.

    If the token is expired or about to expire, automatically refreshes it
    using the refresh token before returning.

    Args:
        db: SQLAlchemy database session

    Returns:
        Valid access token string

    Raises:
        ClientSyncAuthError: If no token exists or refresh fails
    """
    # Query for Conta Azul token
    token_record = db.query(IntegrationToken).filter_by(
        service="conta_azul"
    ).first()

    if not token_record:
        raise ClientSyncAuthError(
            "Conta Azul not connected. Complete OAuth flow first via /api/auth/conta-azul/authorize"
        )

    # Check if token needs refresh
    if token_record.is_expired():
        logger.info("Access token expired, refreshing...")

        try:
            conta_azul_service = ContaAzulService()
            new_token_data = await conta_azul_service.refresh_access_token(
                refresh_token=token_record.refresh_token
            )

            # Update token in database
            token_record.access_token = new_token_data["access_token"]
            token_record.refresh_token = new_token_data.get("refresh_token", token_record.refresh_token)
            token_record.expires_at = datetime.fromisoformat(new_token_data["expires_at"])
            db.commit()

            logger.info("Access token refreshed successfully")
            return token_record.access_token

        except ContaAzulAuthError as e:
            raise ClientSyncAuthError(f"Failed to refresh Conta Azul token: {e}")

    return token_record.access_token


async def _sync_single_client(db: Session, customer_data: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Synchronize a single customer from Conta Azul to local database.

    Implements upsert pattern: if client with matching CPF/CNPJ or conta_azul_id
    exists, update it; otherwise create new record.

    Args:
        db: SQLAlchemy database session
        customer_data: Customer data from Conta Azul API

    Returns:
        Tuple of (created: bool, updated: bool) indicating operation performed

    Raises:
        ClientSyncDataError: If customer data is invalid or missing required fields
    """
    try:
        # Extract and validate required fields from Conta Azul customer data
        conta_azul_id = customer_data.get("id")
        if not conta_azul_id:
            raise ClientSyncDataError("Customer missing required 'id' field")

        # Map Conta Azul fields to Client model fields
        # Conta Azul API structure may vary - adjust field mappings as needed
        name = customer_data.get("name") or customer_data.get("person_name", "")
        if not name:
            raise ClientSyncDataError(f"Customer {conta_azul_id} missing name")

        # CPF/CNPJ from Conta Azul (may be in 'document' or 'cpf_cnpj' field)
        cpf_cnpj = (
            customer_data.get("document") or
            customer_data.get("cpf_cnpj") or
            customer_data.get("person_cpf") or
            customer_data.get("company_cnpj") or
            ""
        )

        if not cpf_cnpj:
            raise ClientSyncDataError(f"Customer {conta_azul_id} missing CPF/CNPJ")

        # Extract optional fields
        email = customer_data.get("email", "")
        phone = customer_data.get("phone") or customer_data.get("mobile_phone", "")

        # Address information (may be nested in 'address' object)
        address = customer_data.get("address", {}) or {}
        address_street = address.get("street", "")
        address_city = address.get("city", "")
        address_state = address.get("state", "")
        address_zip = address.get("zip_code", "")

        notes = customer_data.get("notes", "")

        # Check if client already exists (by CPF/CNPJ or conta_azul_id)
        existing_client = db.query(Client).filter(
            (Client.cpf_cnpj == cpf_cnpj) | (Client.conta_azul_id == str(conta_azul_id))
        ).first()

        current_time = datetime.utcnow()

        if existing_client:
            # Update existing client
            existing_client.name = name
            existing_client.email = email or existing_client.email
            existing_client.phone = phone or existing_client.phone
            existing_client.cpf_cnpj = cpf_cnpj
            existing_client.address_street = address_street or existing_client.address_street
            existing_client.address_city = address_city or existing_client.address_city
            existing_client.address_state = address_state or existing_client.address_state
            existing_client.address_zip = address_zip or existing_client.address_zip
            existing_client.conta_azul_id = str(conta_azul_id)
            existing_client.notes = notes or existing_client.notes
            existing_client.last_synced_at = current_time

            logger.debug(f"Updated existing client: {name} (CPF/CNPJ: {cpf_cnpj})")
            return (False, True)  # Not created, but updated

        else:
            # Create new client
            new_client = Client(
                name=name,
                email=email if email else None,
                phone=phone if phone else None,
                cpf_cnpj=cpf_cnpj,
                address_street=address_street if address_street else None,
                address_city=address_city if address_city else None,
                address_state=address_state if address_state else None,
                address_zip=address_zip if address_zip else None,
                conta_azul_id=str(conta_azul_id),
                notes=notes if notes else None,
                last_synced_at=current_time
            )

            db.add(new_client)
            logger.debug(f"Created new client: {name} (CPF/CNPJ: {cpf_cnpj})")
            return (True, False)  # Created, not updated

    except SQLAlchemyError as e:
        logger.error(f"Database error syncing client: {e}")
        raise ClientSyncDataError(f"Database error: {e}")

    except Exception as e:
        logger.error(f"Unexpected error syncing client: {e}")
        raise ClientSyncDataError(f"Unexpected error: {e}")


async def get_sync_status() -> Dict[str, Any]:
    """
    Get the current synchronization status and statistics.

    Returns:
        Dict containing:
            - last_sync_time: timestamp of last successful sync (or None)
            - total_clients: total number of clients in database
            - synced_clients: number of clients synced from Conta Azul
            - local_only_clients: number of clients not in Conta Azul
            - is_connected: whether Conta Azul OAuth token exists

    Example:
        >>> status = await get_sync_status()
        >>> if status["is_connected"]:
        ...     print(f"Last sync: {status['last_sync_time']}")
    """
    db: Session = SessionLocal()
    try:
        # Check if Conta Azul is connected
        token = db.query(IntegrationToken).filter_by(service="conta_azul").first()
        is_connected = token is not None and not token.is_expired()

        # Count clients
        total_clients = db.query(Client).count()
        synced_clients = db.query(Client).filter(
            Client.conta_azul_id.isnot(None)
        ).count()
        local_only_clients = total_clients - synced_clients

        # Get last sync time
        last_synced = db.query(Client).filter(
            Client.last_synced_at.isnot(None)
        ).order_by(Client.last_synced_at.desc()).first()

        last_sync_time = last_synced.last_synced_at.isoformat() if last_synced else None

        return {
            "is_connected": is_connected,
            "last_sync_time": last_sync_time,
            "total_clients": total_clients,
            "synced_clients": synced_clients,
            "local_only_clients": local_only_clients,
            "timestamp": datetime.utcnow().isoformat()
        }

    finally:
        db.close()
