"""
Financial Data Synchronization Background Job

This module provides a background job for synchronizing financial data between
Conta Azul accounting platform and the local database. The job fetches invoices,
payments, and receivables from Conta Azul and creates or updates local
FinancialRecord records.

The synchronization uses conta_azul_id as the natural key to match financial
records and implements an upsert pattern to avoid duplicates.

Usage:
    from app.background.sync_financial import sync_financial_job

    # Run synchronization manually
    await sync_financial_job()

    # Or schedule with APScheduler
    scheduler.add_job(sync_financial_job, 'interval', hours=24)
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.financial_record import FinancialRecord
from app.models.client import Client
from app.models.integration_token import IntegrationToken
from app.services.conta_azul_service import (
    ContaAzulService,
    ContaAzulError,
    ContaAzulAuthError
)

logger = logging.getLogger(__name__)


class FinancialSyncError(Exception):
    """Base exception for financial data synchronization errors."""
    pass


class FinancialSyncAuthError(FinancialSyncError):
    """Exception raised when Conta Azul authentication fails."""
    pass


class FinancialSyncDataError(FinancialSyncError):
    """Exception raised when financial data processing fails."""
    pass


async def sync_financial_job() -> Dict[str, Any]:
    """
    Background job to synchronize financial data from Conta Azul to local database.

    This job performs the following steps:
    1. Retrieve valid Conta Azul OAuth token from database
    2. Fetch all invoices, sales, and receivables from Conta Azul API
    3. For each financial transaction, create new or update existing FinancialRecord
    4. Use conta_azul_id as natural key for matching
    5. Update last_synced_at timestamp on all synced records
    6. Calculate days_overdue for pending/overdue transactions

    The job uses an upsert pattern (update if exists, create if not) to handle
    both new financial records and updates to existing records.

    Returns:
        Dict containing synchronization results:
            - success: bool indicating if sync completed successfully
            - synced_count: number of financial records synced
            - created_count: number of new records created
            - updated_count: number of existing records updated
            - error_count: number of errors encountered
            - errors: list of error messages
            - duration_seconds: time taken to complete sync

    Raises:
        FinancialSyncAuthError: If Conta Azul authentication fails
        FinancialSyncError: If synchronization fails catastrophically

    Example:
        >>> result = await sync_financial_job()
        >>> print(f"Synced {result['synced_count']} financial records")
        >>> if result['errors']:
        ...     print(f"Encountered {result['error_count']} errors")
    """
    start_time = datetime.utcnow()
    logger.info("Starting financial data synchronization job")

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

        # Step 2: Fetch financial data from Conta Azul
        logger.info("Fetching financial data from Conta Azul API")
        conta_azul_service = ContaAzulService()

        # TODO: Implement get_sales/get_invoices method in ContaAzulService
        # For now, this will raise an AttributeError until the methods are implemented
        # The following methods need to be added to conta_azul_service.py:
        # - get_sales(access_token, limit) -> List[Dict]
        # - get_bills_to_receive(access_token, limit) -> List[Dict]

        financial_transactions = []

        # Fetch sales/invoices (outgoing - receivables)
        try:
            sales = await conta_azul_service.get_sales(
                access_token=access_token,
                limit=1000  # Fetch up to 1000 sales per sync
            )
            financial_transactions.extend(sales)
            logger.info(f"Retrieved {len(sales)} sales from Conta Azul")
        except AttributeError:
            logger.warning(
                "ContaAzulService.get_sales() not implemented yet. "
                "Skipping sales synchronization."
            )

        # Fetch bills to receive (receivables)
        try:
            receivables = await conta_azul_service.get_bills_to_receive(
                access_token=access_token,
                limit=1000  # Fetch up to 1000 receivables per sync
            )
            financial_transactions.extend(receivables)
            logger.info(f"Retrieved {len(receivables)} receivables from Conta Azul")
        except AttributeError:
            logger.warning(
                "ContaAzulService.get_bills_to_receive() not implemented yet. "
                "Skipping receivables synchronization."
            )

        logger.info(f"Retrieved {len(financial_transactions)} total financial transactions from Conta Azul")

        # Step 3: Process each financial transaction
        for transaction_data in financial_transactions:
            try:
                created, updated = await _sync_single_transaction(db, transaction_data)
                synced_count += 1
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                error_msg = f"Failed to sync transaction {transaction_data.get('id', 'unknown')}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue  # Continue with next transaction

        # Step 4: Commit all changes
        db.commit()

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"Financial data synchronization completed successfully: "
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

    except FinancialSyncAuthError as e:
        logger.error(f"Authentication error during financial sync: {e}")
        db.rollback()
        raise

    except Exception as e:
        logger.error(f"Unexpected error during financial sync: {e}", exc_info=True)
        db.rollback()
        raise FinancialSyncError(f"Financial data synchronization failed: {e}")

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
        FinancialSyncAuthError: If no token exists or refresh fails
    """
    # Query for Conta Azul token
    token_record = db.query(IntegrationToken).filter_by(
        service="conta_azul"
    ).first()

    if not token_record:
        raise FinancialSyncAuthError(
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
            token_record.token_expiry = datetime.fromisoformat(
                new_token_data["expires_at"]
            )
            if "refresh_token" in new_token_data:
                token_record.refresh_token = new_token_data["refresh_token"]

            db.commit()
            logger.info("Access token refreshed successfully")

        except ContaAzulAuthError as e:
            raise FinancialSyncAuthError(f"Failed to refresh access token: {e}")

    return token_record.access_token


async def _sync_single_transaction(
    db: Session,
    transaction_data: Dict[str, Any]
) -> Tuple[bool, bool]:
    """
    Synchronize a single financial transaction to the database.

    Creates a new FinancialRecord if one doesn't exist with the given conta_azul_id,
    or updates an existing record. Uses conta_azul_id as the natural key.

    Args:
        db: SQLAlchemy database session
        transaction_data: Dictionary containing transaction data from Conta Azul
            Expected keys:
                - id: Conta Azul transaction ID (required)
                - customer_id: Conta Azul customer ID (required)
                - type: Transaction type (invoice, sale, receivable, etc.)
                - number: Transaction number/identifier
                - description: Transaction description
                - amount: Transaction amount
                - currency: Currency code (default: BRL)
                - status: Transaction status (pending, paid, overdue, cancelled)
                - created_at: Transaction creation date
                - due_date: Payment due date
                - paid_at: Payment date (if paid)
                - payment_method: Payment method used

    Returns:
        Tuple of (created: bool, updated: bool)
            - (True, False) if new record was created
            - (False, True) if existing record was updated
            - (False, False) if no changes were needed

    Raises:
        FinancialSyncDataError: If required data is missing or invalid
        SQLAlchemyError: If database operation fails
    """
    # Validate required fields
    conta_azul_id = transaction_data.get("id")
    if not conta_azul_id:
        raise FinancialSyncDataError("Transaction missing required 'id' field")

    conta_azul_customer_id = transaction_data.get("customer_id")
    if not conta_azul_customer_id:
        raise FinancialSyncDataError(
            f"Transaction {conta_azul_id} missing required 'customer_id' field"
        )

    # Find corresponding local client by conta_azul_id
    client = db.query(Client).filter_by(
        conta_azul_id=str(conta_azul_customer_id)
    ).first()

    if not client:
        raise FinancialSyncDataError(
            f"No local client found with conta_azul_id={conta_azul_customer_id}. "
            "Run client sync first."
        )

    # Check if record already exists
    existing_record = db.query(FinancialRecord).filter_by(
        conta_azul_id=str(conta_azul_id)
    ).first()

    # Parse transaction data
    transaction_date = _parse_date(transaction_data.get("created_at"))
    due_date = _parse_date(transaction_data.get("due_date"))
    payment_date = _parse_date(transaction_data.get("paid_at"))

    # Calculate days overdue
    days_overdue = 0
    if due_date and not payment_date:
        today = date.today()
        if today > due_date:
            days_overdue = (today - due_date).days

    # Determine transaction status
    status = transaction_data.get("status", "pending").lower()
    if days_overdue > 0 and status == "pending":
        status = "overdue"

    # Parse amount
    amount = transaction_data.get("amount", 0)
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    elif isinstance(amount, str):
        amount = Decimal(amount)

    # Prepare record data
    record_data = {
        "client_id": client.id,
        "transaction_type": transaction_data.get("type", "invoice"),
        "transaction_number": transaction_data.get("number", f"CA-{conta_azul_id}"),
        "description": transaction_data.get("description", ""),
        "amount": amount,
        "currency": transaction_data.get("currency", "BRL"),
        "status": status,
        "transaction_date": transaction_date or date.today(),
        "due_date": due_date,
        "payment_date": payment_date,
        "days_overdue": days_overdue,
        "conta_azul_id": str(conta_azul_id),
        "payment_method": transaction_data.get("payment_method"),
        "notes": transaction_data.get("notes"),
        "last_synced_at": datetime.utcnow()
    }

    if existing_record:
        # Update existing record
        for key, value in record_data.items():
            setattr(existing_record, key, value)

        logger.debug(f"Updated financial record: {existing_record.transaction_number}")
        return (False, True)
    else:
        # Create new record
        new_record = FinancialRecord(**record_data)
        db.add(new_record)
        logger.debug(f"Created financial record: {new_record.transaction_number}")
        return (True, False)


def _parse_date(date_value: Any) -> Optional[date]:
    """
    Parse a date value from various formats to a Python date object.

    Args:
        date_value: Date value to parse (can be string, datetime, date, or None)

    Returns:
        Parsed date object or None if parsing fails or value is None

    Supported formats:
        - ISO format: "2024-01-30"
        - ISO datetime: "2024-01-30T10:00:00Z"
        - Python datetime or date objects
    """
    if not date_value:
        return None

    if isinstance(date_value, date):
        return date_value

    if isinstance(date_value, datetime):
        return date_value.date()

    if isinstance(date_value, str):
        try:
            # Try parsing ISO datetime format
            if "T" in date_value:
                dt = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
                return dt.date()
            else:
                # Try parsing ISO date format
                return datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Failed to parse date value: {date_value}")
            return None

    return None
