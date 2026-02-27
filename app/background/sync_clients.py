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
import hashlib
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.client import Client
from app.models.integration_token import IntegrationToken
from app.services.conta_azul_service import (
    ContaAzulService,
    ContaAzulError,
    ContaAzulAuthError,
    ContaAzulInvalidGrantError,
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


def _truncate(value: Any, max_len: int) -> str:
    """Convert value to string and enforce max length for DB compatibility."""
    if value is None:
        return ""
    text = str(value).strip()
    return text[:max_len]


def _mask_identifier(value: Any) -> str:
    """Mask identifiers before logging to avoid exposing full external IDs."""
    text = _truncate(value, 120)
    if not text:
        return "unknown"
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def _normalize_tax_id(raw_value: Any, conta_azul_id: Any) -> str:
    """
    Normalize CPF/CNPJ/document value to fit Client.cpf_cnpj (varchar(20)).

    Preference order:
    1) Valid CPF/CNPJ digits (11/14)
    2) Digits-only version up to 20 chars
    3) Sanitized alphanumeric document up to 20 chars
    4) Deterministic placeholder from Conta Azul ID (always <=20)
    """
    raw = _truncate(raw_value, 255)
    digits = "".join(ch for ch in raw if ch.isdigit())

    if len(digits) in (11, 14):
        return digits

    if digits and len(digits) <= 20:
        return digits

    cleaned = re.sub(r"[^A-Za-z0-9._/-]", "", raw)
    if cleaned:
        return cleaned[:20]

    # Stable fallback for customers without document
    digest = hashlib.sha1(str(conta_azul_id).encode("utf-8")).hexdigest()[:17]
    return f"CA-{digest}"


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
            - success: bool indicating if sync completed with zero errors
            - partial_success: bool indicating partial completion with errors
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
    start_time = datetime.now(timezone.utc)
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

        # Log first customer for debugging field names
        if customers:
            first = customers[0]
            logger.info(f"First customer keys: {list(first.keys())}")
            logger.info(
                "First customer sample (masked): id=%s, has_nome=%s, has_cpf=%s, has_cnpj=%s",
                _mask_identifier(first.get("id")),
                bool(first.get("nome") or first.get("name")),
                bool(first.get("cpf")),
                bool(first.get("cnpj")),
            )

        # Step 3: Process each customer
        for customer_data in customers:
            try:
                # Isolate each customer in a SAVEPOINT so one bad record
                # does not abort the entire synchronization batch.
                with db.begin_nested():
                    created, updated = await _sync_single_client(db, customer_data)
                    # Force constraint checks inside the savepoint boundary.
                    db.flush()
                synced_count += 1
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                error_msg = (
                    f"Failed to sync client { _mask_identifier(customer_data.get('id', 'unknown')) }: {e}"
                )
                logger.error(error_msg)
                errors.append(error_msg)
                continue  # Continue with next customer

        # Step 4: Commit all changes
        db.commit()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        success = error_count == 0
        partial_success = synced_count > 0 and error_count > 0
        status_label = "successfully" if success else "with issues"
        logger.info(
            f"Client synchronization completed {status_label}: "
            f"{synced_count} synced ({created_count} created, {updated_count} updated), "
            f"{error_count} errors in {duration:.2f}s"
        )

        return {
            "success": success,
            "partial_success": partial_success,
            "synced_count": synced_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors,
            "duration_seconds": duration,
            "timestamp": datetime.now(timezone.utc).isoformat()
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

        except ContaAzulInvalidGrantError:
            raise ClientSyncAuthError(
                "Refresh token inválido (invalid_grant). "
                "Reautorize via GET /api/auth/conta-azul/authorize"
            )
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
        # Log first customer data for debugging field names
        logger.debug(f"Raw customer data keys: {list(customer_data.keys())}")

        # Extract and validate required fields from Conta Azul API v2 (Portuguese field names)
        conta_azul_id = customer_data.get("id")
        if not conta_azul_id:
            raise ClientSyncDataError("Customer missing required 'id' field")

        # Map Conta Azul v2 fields to Client model fields
        # API v2 uses Portuguese: nome, cpf, cnpj, telefone, celular, endereco, etc.
        raw_name = (
            customer_data.get("nome") or
            customer_data.get("name") or
            customer_data.get("razao_social") or
            customer_data.get("nome_fantasia") or
            customer_data.get("person_name", "")
        )
        if not raw_name:
            logger.warning(
                "Customer %s missing name, keys: %s",
                _mask_identifier(conta_azul_id),
                list(customer_data.keys()),
            )
            # Try to build name from available fields
            raw_name = f"Cliente #{conta_azul_id}"
        name = _truncate(raw_name, 255)

        # CPF/CNPJ from Conta Azul v2
        raw_cpf_cnpj = (
            customer_data.get("cpf") or
            customer_data.get("cnpj") or
            customer_data.get("documento") or
            customer_data.get("document") or
            customer_data.get("cpf_cnpj") or
            customer_data.get("person_cpf") or
            customer_data.get("company_cnpj") or
            ""
        )
        cpf_cnpj = _normalize_tax_id(raw_cpf_cnpj, conta_azul_id)
        if not raw_cpf_cnpj:
            logger.warning(
                "Customer %s missing CPF/CNPJ - using deterministic placeholder",
                _mask_identifier(conta_azul_id),
            )

        # Extract optional fields (try both PT and EN names)
        email = customer_data.get("email") or customer_data.get("emails", [{}])[0].get("email", "") if isinstance(customer_data.get("emails"), list) and customer_data.get("emails") else customer_data.get("email", "")
        phone = (
            customer_data.get("telefone") or
            customer_data.get("celular") or
            customer_data.get("phone") or
            customer_data.get("mobile_phone") or
            ""
        )
        # Handle phone as list/dict
        telefones = customer_data.get("telefones", [])
        if telefones and isinstance(telefones, list) and not phone:
            first_tel = telefones[0] if telefones else {}
            if isinstance(first_tel, dict):
                phone = first_tel.get("numero", "") or first_tel.get("telefone", "")
            elif isinstance(first_tel, str):
                phone = first_tel

        email = _truncate(email, 255)
        phone = _truncate(phone, 20)

        # Address information (may be nested in 'endereco' object)
        address = customer_data.get("endereco", {}) or customer_data.get("address", {}) or {}
        address_street = _truncate(
            address.get("logradouro", "") or address.get("rua", "") or address.get("street", ""),
            255,
        )
        address_city = _truncate(
            address.get("cidade", "") or address.get("city", ""),
            100,
        )
        address_state = _truncate(
            (address.get("estado", "") or address.get("uf", "") or address.get("state", "")).upper(),
            2,
        )
        address_zip = _truncate(address.get("cep", "") or address.get("zip_code", ""), 10)

        notes = customer_data.get("observacoes", "") or customer_data.get("notes", "")
        conta_azul_id_str = _truncate(conta_azul_id, 100)

        # Check if client already exists (by CPF/CNPJ or conta_azul_id)
        existing_client = db.query(Client).filter(
            (Client.cpf_cnpj == cpf_cnpj) | (Client.conta_azul_id == conta_azul_id_str)
        ).first()

        current_time = datetime.now(timezone.utc)

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
            existing_client.conta_azul_id = conta_azul_id_str
            existing_client.notes = notes or existing_client.notes
            existing_client.last_synced_at = current_time

            logger.debug(
                "Updated existing client from Conta Azul id=%s",
                _mask_identifier(conta_azul_id_str),
            )
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
                conta_azul_id=conta_azul_id_str,
                notes=notes if notes else None,
                last_synced_at=current_time
            )

            db.add(new_client)
            logger.debug(
                "Created new client from Conta Azul id=%s",
                _mask_identifier(conta_azul_id_str),
            )
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
            - sync_freshness: freshness classification (fresh/warning/stale/missing)
            - hours_since_last_sync: hours since last sync (or None)
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
        now = datetime.now(timezone.utc)
        last_synced = db.query(Client).filter(
            Client.last_synced_at.isnot(None)
        ).order_by(Client.last_synced_at.desc()).first()

        last_sync_dt = last_synced.last_synced_at if last_synced else None
        sync_freshness = "missing"
        hours_since_last_sync = None

        if last_sync_dt:
            if last_sync_dt.tzinfo is None:
                last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
            hours_since_last_sync = max(
                0.0,
                (now - last_sync_dt).total_seconds() / 3600.0,
            )
            if hours_since_last_sync > 6:
                sync_freshness = "stale"
            elif hours_since_last_sync > 2:
                sync_freshness = "warning"
            else:
                sync_freshness = "fresh"

        last_sync_time = last_sync_dt.isoformat() if last_sync_dt else None

        return {
            "is_connected": is_connected,
            "last_sync_time": last_sync_time,
            "sync_freshness": sync_freshness,
            "hours_since_last_sync": hours_since_last_sync,
            "total_clients": total_clients,
            "synced_clients": synced_clients,
            "local_only_clients": local_only_clients,
            "timestamp": now.isoformat()
        }

    finally:
        db.close()
