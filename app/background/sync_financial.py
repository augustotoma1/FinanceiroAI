"""
Financial Data Synchronization Background Job

This module provides a background job for synchronizing financial data between
Conta Azul accounting platform and the local database. The job fetches
contas a receber and contas a pagar from Conta Azul and creates or updates
local FinancialRecord records.

The synchronization uses conta_azul_id as the natural key to match financial
records and implements an upsert pattern to avoid duplicates.

Usage:
    from app.background.sync_financial import sync_financial_job

    # Run synchronization manually
    await sync_financial_job()

    # Or schedule with APScheduler
    scheduler.add_job(sync_financial_job, 'interval', hours=24)
"""

import hashlib
import logging
import re
from datetime import datetime, date, timezone, timedelta
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.financial_record import FinancialRecord
from app.models.client import Client
from app.models.integration_token import IntegrationToken
from app.services.conta_azul_service import (
    ContaAzulService,
    ContaAzulError,
    ContaAzulAuthError,
    ContaAzulInvalidGrantError,
)

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_LOOKAHEAD_DAYS = 365
MAX_RECORDS_PER_SOURCE = 500
PAGE_SIZE = 100
PAID_STATUSES = {"QUITADO", "RECEBIDO", "PAGO", "ACQUITTED", "PAID"}
CANCELED_STATUSES = {"CANCELADO", "CANCELED", "VOID"}


class FinancialSyncError(Exception):
    """Base exception for financial data synchronization errors."""
    pass


class FinancialSyncAuthError(FinancialSyncError):
    """Exception raised when Conta Azul authentication fails."""
    pass


class FinancialSyncDataError(FinancialSyncError):
    """Exception raised when financial data processing fails."""
    pass


async def sync_financial_job(
    data_vencimento_de: Optional[str] = None,
    data_vencimento_ate: Optional[str] = None,
    max_records_per_source: int = MAX_RECORDS_PER_SOURCE,
) -> Dict[str, Any]:
    """
    Background job to synchronize financial data from Conta Azul to local database.

    This job performs the following steps:
    1. Retrieve valid Conta Azul OAuth token from database
    2. Fetch contas a receber and contas a pagar from Conta Azul API v2
    3. For each financial event, create new or update existing FinancialRecord
    4. Use a stable source-prefixed conta_azul_id as natural key
    5. Update last_synced_at timestamp on all synced records
    6. Calculate days_overdue for pending/overdue transactions

    The job uses an upsert pattern (update if exists, create if not) to handle
    both new financial records and updates to existing records.

    Args:
        data_vencimento_de: Optional due-date range start (ISO date string).
            If omitted with data_vencimento_ate, uses default rolling window.
        data_vencimento_ate: Optional due-date range end (ISO date string).
            If omitted with data_vencimento_de, uses default rolling window.
        max_records_per_source: Max records fetched for each source (receber/pagar).

    Returns:
        Dict containing synchronization results:
            - success: bool indicating if sync completed successfully
            - partial_success: bool indicating partial completion with errors
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
    start_time = datetime.now(timezone.utc)
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
        data_vencimento_de, data_vencimento_ate = _resolve_sync_window(
            data_vencimento_de=data_vencimento_de,
            data_vencimento_ate=data_vencimento_ate,
        )
        max_records_per_source = max(1, int(max_records_per_source))
        financial_transactions: List[Dict[str, Any]] = []
        source_fetch_errors: List[str] = []
        source_totals: Dict[str, int] = {"receber": 0, "pagar": 0}

        sources = [
            ("receber", "/v1/financeiro/eventos-financeiros/contas-a-receber/buscar"),
            ("pagar", "/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar"),
        ]

        for source_kind, endpoint in sources:
            try:
                items = await _fetch_financial_items_paginated(
                    service=conta_azul_service,
                    access_token=access_token,
                    endpoint=endpoint,
                    data_vencimento_de=data_vencimento_de,
                    data_vencimento_ate=data_vencimento_ate,
                    max_records=max_records_per_source,
                    page_size=PAGE_SIZE,
                )
                source_totals[source_kind] = len(items)
                for item in items:
                    item["_sync_kind"] = source_kind
                    financial_transactions.append(item)
                logger.info(f"Retrieved {len(items)} records from contas a {source_kind}")
            except ContaAzulError as e:
                fetch_error = f"Failed to fetch contas a {source_kind}: {e}"
                source_fetch_errors.append(fetch_error)
                logger.error(fetch_error)

        if not financial_transactions and source_fetch_errors:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return {
                "success": False,
                "partial_success": False,
                "synced_count": 0,
                "created_count": 0,
                "updated_count": 0,
                "error_count": len(source_fetch_errors),
                "errors": source_fetch_errors,
                "source_totals": source_totals,
                "window": {
                    "data_vencimento_de": data_vencimento_de,
                    "data_vencimento_ate": data_vencimento_ate,
                },
                "duration_seconds": duration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        logger.info(
            "Retrieved %s total financial events from Conta Azul "
            "(receber=%s, pagar=%s)",
            len(financial_transactions),
            source_totals["receber"],
            source_totals["pagar"],
        )

        # Step 3: Process each financial event with per-item SAVEPOINT to avoid
        # one broken payload aborting the entire synchronization batch.
        for transaction_data in financial_transactions:
            try:
                with db.begin_nested():
                    created, updated = _sync_single_transaction(db, transaction_data)
                synced_count += 1
                if created:
                    created_count += 1
                elif updated:
                    updated_count += 1

            except Exception as e:
                error_count += 1
                source_kind = _as_text(transaction_data.get("_sync_kind")) or "unknown"
                transaction_id = _as_text(transaction_data.get("id")) or "unknown"
                error_msg = (
                    f"Failed to sync {source_kind} transaction {transaction_id}: {e}"
                )
                logger.error(error_msg)
                errors.append(error_msg)
                continue  # Continue with next transaction

        # Step 4: Commit all changes
        db.commit()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"Financial data synchronization completed successfully: "
            f"{synced_count} synced ({created_count} created, {updated_count} updated), "
            f"{error_count} errors in {duration:.2f}s"
        )
        total_errors = error_count + len(source_fetch_errors)
        success = total_errors == 0
        partial_success = synced_count > 0 and total_errors > 0

        return {
            "success": success,
            "partial_success": partial_success,
            "synced_count": synced_count,
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": total_errors,
            "errors": errors + source_fetch_errors,
            "source_totals": source_totals,
            "window": {
                "data_vencimento_de": data_vencimento_de,
                "data_vencimento_ate": data_vencimento_ate,
            },
            "duration_seconds": duration,
            "timestamp": datetime.now(timezone.utc).isoformat()
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
            token_record.expires_at = datetime.fromisoformat(
                new_token_data["expires_at"]
            )
            if "refresh_token" in new_token_data:
                token_record.refresh_token = new_token_data["refresh_token"]

            db.commit()
            logger.info("Access token refreshed successfully")

        except ContaAzulInvalidGrantError:
            raise FinancialSyncAuthError(
                "Refresh token inválido (invalid_grant). "
                "Reautorize via GET /api/auth/conta-azul/authorize"
            )
        except ContaAzulAuthError as e:
            raise FinancialSyncAuthError(f"Failed to refresh access token: {e}")

    return token_record.access_token


def _sync_single_transaction(
    db: Session,
    transaction_data: Dict[str, Any],
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
    source_kind = _as_text(transaction_data.get("_sync_kind")) or "receber"
    raw_event_id = _extract_event_id(transaction_data)
    if not raw_event_id:
        raise FinancialSyncDataError("Transaction missing required 'id' field")

    person_info = _extract_person_info(transaction_data)
    client = _resolve_or_create_client(
        db=db,
        person_info=person_info,
        source_kind=source_kind,
        event_id=raw_event_id,
    )

    total = _to_decimal(
        transaction_data.get("valor")
        or transaction_data.get("valor_total")
        or transaction_data.get("amount")
        or transaction_data.get("total")
    )
    not_paid = _to_decimal(transaction_data.get("nao_pago"))
    paid = _to_decimal(transaction_data.get("pago"))
    open_amount = not_paid if not_paid > 0 else max(total - paid, Decimal("0"))
    amount = total if total > 0 else max(open_amount + paid, Decimal("0"))

    due_date = _parse_date(
        transaction_data.get("data_vencimento") or transaction_data.get("due_date")
    )
    transaction_date = _parse_date(
        transaction_data.get("data_competencia")
        or transaction_data.get("data_emissao")
        or transaction_data.get("data_lancamento")
        or transaction_data.get("created_at")
    ) or due_date or date.today()
    payment_date = _parse_date(
        transaction_data.get("data_pagamento") or transaction_data.get("paid_at")
    )

    status_raw = _as_text(
        transaction_data.get("status_traduzido") or transaction_data.get("status")
    ).upper()
    status = _normalize_status(
        status_raw=status_raw,
        due_date=due_date,
        payment_date=payment_date,
        open_amount=open_amount,
        paid_amount=paid,
    )
    days_overdue = _calculate_days_overdue(due_date=due_date, payment_date=payment_date)

    raw_number = _as_text(
        transaction_data.get("numero")
        or transaction_data.get("number")
        or transaction_data.get("codigo")
        or transaction_data.get("documento_numero")
    )
    transaction_number = _build_transaction_number(
        source_kind=source_kind,
        event_id=raw_event_id,
        raw_number=raw_number,
    )

    description = _as_text(
        transaction_data.get("descricao")
        or transaction_data.get("description")
        or transaction_data.get("observacao")
    ) or f"Conta a {'receber' if source_kind == 'receber' else 'pagar'}"
    payment_method = _normalize_payment_method(transaction_data)
    currency = (_as_text(transaction_data.get("currency") or transaction_data.get("moeda")) or "BRL").upper()[:3]

    source_prefixed_id = _build_source_event_id(source_kind=source_kind, event_id=raw_event_id)

    notes_chunks = []
    if raw_number and raw_number != transaction_number:
        notes_chunks.append(f"Numero original: {raw_number}")
    if status_raw:
        notes_chunks.append(f"Status original: {status_raw}")
    notes_chunks.extend(_build_financial_dimensions_notes(transaction_data))
    notes_chunks.append(f"Fonte: contas a {source_kind}")
    notes = " | ".join(notes_chunks)

    record_data = {
        "client_id": client.id,
        "transaction_type": "receivable" if source_kind == "receber" else "payable",
        "transaction_number": transaction_number,
        "description": _truncate(description, 10000),
        "amount": amount,
        "currency": currency,
        "status": status,
        "transaction_date": transaction_date,
        "due_date": due_date,
        "payment_date": payment_date,
        "days_overdue": days_overdue,
        "conta_azul_id": source_prefixed_id,
        "payment_method": payment_method,
        "notes": _truncate(notes, 10000),
        "last_synced_at": datetime.now(timezone.utc),
    }

    existing_record = db.query(FinancialRecord).filter_by(conta_azul_id=source_prefixed_id).first()
    if existing_record:
        for key, value in record_data.items():
            setattr(existing_record, key, value)
        logger.debug(f"Updated financial record: {existing_record.transaction_number}")
        return (False, True)

    new_record = FinancialRecord(**record_data)
    db.add(new_record)
    logger.debug(f"Created financial record: {new_record.transaction_number}")
    return (True, False)


def _build_sync_window() -> Tuple[str, str]:
    """Build default due date window required by Conta Azul financial search API."""
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    end_date = today + timedelta(days=DEFAULT_LOOKAHEAD_DAYS)
    return start_date.isoformat(), end_date.isoformat()


def _resolve_sync_window(
    data_vencimento_de: Optional[str],
    data_vencimento_ate: Optional[str],
) -> Tuple[str, str]:
    """
    Resolve sync due-date window with validation.

    If both values are missing, default rolling window is used.
    If one value is provided, both become mandatory.
    """
    if not data_vencimento_de and not data_vencimento_ate:
        return _build_sync_window()

    if not data_vencimento_de or not data_vencimento_ate:
        raise FinancialSyncDataError(
            "data_vencimento_de e data_vencimento_ate devem ser informados juntos"
        )

    start_date = _parse_date(data_vencimento_de)
    end_date = _parse_date(data_vencimento_ate)
    if not start_date or not end_date:
        raise FinancialSyncDataError(
            "Periodo invalido. Use datas no formato YYYY-MM-DD."
        )
    if start_date > end_date:
        raise FinancialSyncDataError("Data inicial maior que a data final.")

    return start_date.isoformat(), end_date.isoformat()


def _extract_items(response: Any) -> List[Dict[str, Any]]:
    """Extract list-like payloads from heterogeneous Conta Azul responses."""
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("data", "items", "content", "itens", "results", "contas"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        if "id" in response:
            return [response]
    return []


async def _fetch_financial_items_paginated(
    service: ContaAzulService,
    access_token: str,
    endpoint: str,
    data_vencimento_de: str,
    data_vencimento_ate: str,
    max_records: int,
    page_size: int,
) -> List[Dict[str, Any]]:
    """Fetch all available pages from Conta Azul financial search endpoints."""
    all_items: List[Dict[str, Any]] = []
    page = 1
    page_size = max(1, min(page_size, 100))
    max_records = max(1, max_records)

    while len(all_items) < max_records:
        request_size = min(page_size, max_records - len(all_items))
        params: Dict[str, Any] = {
            "pagina": page,
            "tamanho_pagina": request_size,
            "data_vencimento_de": data_vencimento_de,
            "data_vencimento_ate": data_vencimento_ate,
        }
        response = await service.make_api_request(
            endpoint=endpoint,
            access_token=access_token,
            method="GET",
            params=params,
        )
        items = service._extract_items(response) if hasattr(service, "_extract_items") else _extract_items(response)
        if not items:
            break
        all_items.extend(items)
        if len(items) < request_size:
            break
        page += 1

    return all_items


def _extract_event_id(transaction_data: Dict[str, Any]) -> str:
    """Extract stable Conta Azul event id from heterogeneous payloads."""
    for key in ("id", "evento_financeiro_id", "event_id", "codigo"):
        value = transaction_data.get(key)
        text = _as_text(value)
        if text:
            return _truncate(text, 80)
    return ""


def _build_source_event_id(source_kind: str, event_id: str) -> str:
    """Build source-prefixed unique id persisted in financial_records.conta_azul_id."""
    return _truncate(f"{source_kind}:{event_id}", 100)


def _build_transaction_number(source_kind: str, event_id: str, raw_number: str) -> str:
    """Build deterministic transaction number that satisfies unique constraints."""
    base = _as_text(raw_number) or event_id
    prefix = "REC" if source_kind == "receber" else "PAG"
    return _truncate(f"CA-{prefix}-{base}", 100)


def _extract_person_info(transaction_data: Dict[str, Any]) -> Dict[str, str]:
    """Normalize counterparty fields from mixed Conta Azul payloads."""
    info: Dict[str, str] = {
        "id": "",
        "name": "",
        "document": "",
        "email": "",
        "phone": "",
    }

    person = (
        transaction_data.get("pessoa")
        or transaction_data.get("cliente")
        or transaction_data.get("fornecedor")
        or {}
    )
    if isinstance(person, dict):
        info["id"] = _as_text(person.get("id") or person.get("pessoa_id") or person.get("codigo"))
        info["name"] = _as_text(
            person.get("nome")
            or person.get("razao_social")
            or person.get("nome_fantasia")
        )
        info["document"] = _as_text(
            person.get("cpf")
            or person.get("cnpj")
            or person.get("cpf_cnpj")
            or person.get("documento")
            or person.get("document")
        )
        info["email"] = _as_text(person.get("email"))
        info["phone"] = _as_text(person.get("telefone") or person.get("celular"))
    elif isinstance(person, str):
        info["name"] = _as_text(person)

    if not info["id"]:
        info["id"] = _as_text(
            transaction_data.get("pessoa_id")
            or transaction_data.get("cliente_id")
            or transaction_data.get("fornecedor_id")
            or transaction_data.get("customer_id")
            or transaction_data.get("supplier_id")
        )
    if not info["name"]:
        info["name"] = _as_text(
            transaction_data.get("nome_pessoa")
            or transaction_data.get("cliente")
            or transaction_data.get("fornecedor")
        )
    if not info["document"]:
        info["document"] = _as_text(
            transaction_data.get("cpf")
            or transaction_data.get("cnpj")
            or transaction_data.get("cpf_cnpj")
            or transaction_data.get("documento")
            or transaction_data.get("document")
        )
    if not info["email"]:
        info["email"] = _as_text(transaction_data.get("email"))
    if not info["phone"]:
        info["phone"] = _as_text(
            transaction_data.get("telefone")
            or transaction_data.get("celular")
            or transaction_data.get("phone")
        )

    return info


def _resolve_or_create_client(
    db: Session,
    person_info: Dict[str, str],
    source_kind: str,
    event_id: str,
) -> Client:
    """Resolve local client from payload fields or create deterministic placeholder."""
    person_id = _truncate(person_info.get("id"), 100)
    raw_name = _truncate(person_info.get("name"), 255)
    fallback_seed = f"{source_kind}:{person_id or raw_name.lower() or event_id}"
    normalized_tax_id = _normalize_tax_id(person_info.get("document"), fallback_seed)
    normalized_email = _truncate(person_info.get("email"), 255)
    normalized_phone = _truncate(person_info.get("phone"), 20)
    display_name = raw_name or f"{'Cliente' if source_kind == 'receber' else 'Fornecedor'} {event_id}"

    client: Optional[Client] = None
    if person_id:
        client = db.query(Client).filter_by(conta_azul_id=person_id).first()
    if not client and normalized_tax_id:
        client = db.query(Client).filter_by(cpf_cnpj=normalized_tax_id).first()
    if not client and normalized_email:
        client = db.query(Client).filter_by(email=normalized_email).first()
    if not client and display_name:
        client = db.query(Client).filter_by(name=display_name).first()

    now = datetime.now(timezone.utc)

    if client:
        if person_id and not client.conta_azul_id:
            client.conta_azul_id = person_id
        if normalized_email and not client.email:
            client.email = normalized_email
        if normalized_phone and not client.phone:
            client.phone = normalized_phone
        client.last_synced_at = now
        return client

    generated_conta_azul_id = person_id or _truncate(
        f"{source_kind}-person-{hashlib.sha1(fallback_seed.encode('utf-8')).hexdigest()[:24]}",
        100,
    )
    new_client = Client(
        name=display_name,
        email=normalized_email or None,
        phone=normalized_phone or None,
        cpf_cnpj=normalized_tax_id,
        conta_azul_id=generated_conta_azul_id,
        notes=f"Criado automaticamente pelo sync financeiro ({source_kind})",
        last_synced_at=now,
    )
    db.add(new_client)
    db.flush()  # Ensures new_client.id is available for FK usage
    return new_client


def _normalize_status(
    status_raw: str,
    due_date: Optional[date],
    payment_date: Optional[date],
    open_amount: Decimal,
    paid_amount: Decimal,
) -> str:
    """Map Conta Azul status variants to local normalized status values."""
    if status_raw in CANCELED_STATUSES:
        return "cancelled"

    if status_raw in PAID_STATUSES or payment_date or (open_amount <= 0 and paid_amount > 0):
        return "paid"

    if due_date and due_date < date.today():
        return "overdue"

    return "pending"


def _normalize_payment_method(transaction_data: Dict[str, Any]) -> Optional[str]:
    """
    Normalize payment method values from Conta Azul payload variants.

    Specifically normalizes PIX legacy enum:
    - PAGAMENTO_INSTANTANEO -> PIX_PAGAMENTO_INSTANTANEO
    """
    raw = (
        transaction_data.get("forma_pagamento")
        or transaction_data.get("payment_method")
        or transaction_data.get("tipo_pagamento")
    )

    if isinstance(raw, dict):
        raw = (
            raw.get("tipo_pagamento")
            or raw.get("tipo")
            or raw.get("descricao")
            or raw.get("valor")
        )

    normalized = ContaAzulService.normalize_payment_type(raw)
    if not normalized:
        return None
    return _truncate(normalized, 50) or None


def _build_financial_dimensions_notes(transaction_data: Dict[str, Any]) -> List[str]:
    """Build notes chunk with Conta Azul financial dimensions (competencia/custos/categorias)."""
    notes: List[str] = []

    competencia = _parse_date(transaction_data.get("data_competencia"))
    if competencia:
        notes.append(f"Competencia: {competencia.isoformat()}")

    centros_raw = (
        transaction_data.get("centros_de_custo")
        or transaction_data.get("centrosDeCusto")
        or transaction_data.get("centro_de_custo")
        or transaction_data.get("id_centro_custo")
    )
    centros = _extract_dimension_labels(centros_raw)
    if centros:
        notes.append(f"Centros de custo: {', '.join(centros[:5])}")

    categorias_raw = (
        transaction_data.get("categorias")
        or transaction_data.get("categorias_financeiras")
        or transaction_data.get("categoria")
    )
    categorias = _extract_dimension_labels(categorias_raw)
    if categorias:
        notes.append(f"Categorias: {', '.join(categorias[:5])}")

    return notes


def _extract_dimension_labels(raw_value: Any) -> List[str]:
    """Extract human-readable labels from list/dict/string dimension payloads."""
    if raw_value is None:
        return []

    if isinstance(raw_value, dict):
        values = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    else:
        text = _as_text(raw_value)
        return [text] if text else []

    labels: List[str] = []
    for entry in values:
        if isinstance(entry, dict):
            entry_id = _as_text(
                entry.get("id")
                or entry.get("id_centro_custo")
                or entry.get("id_categoria")
            )
            entry_label = _as_text(
                entry.get("nome")
                or entry.get("descricao")
                or entry.get("categoria")
                or entry.get("centro_custo")
            )
            if entry_id and entry_label and entry_id != entry_label:
                labels.append(f"{entry_label} ({entry_id})")
            elif entry_label:
                labels.append(entry_label)
            elif entry_id:
                labels.append(entry_id)
        else:
            text = _as_text(entry)
            if text:
                labels.append(text)

    # Preserve order while deduplicating
    unique_labels: List[str] = []
    for label in labels:
        if label not in unique_labels:
            unique_labels.append(label)
    return unique_labels


def _calculate_days_overdue(
    due_date: Optional[date],
    payment_date: Optional[date],
) -> int:
    """Calculate days overdue for open transactions."""
    if not due_date or payment_date:
        return 0
    today = date.today()
    if today <= due_date:
        return 0
    return (today - due_date).days


def _as_text(value: Any) -> str:
    """Convert arbitrary values to stripped text safely."""
    if value is None:
        return ""
    return str(value).strip()


def _truncate(value: Any, max_len: int) -> str:
    """Convert value to string and enforce max length for DB compatibility."""
    return _as_text(value)[:max_len]


def _to_decimal(value: Any) -> Decimal:
    """Convert value to Decimal with safe fallbacks for malformed payloads."""
    if value is None or value == "":
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = _as_text(value).replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        return Decimal(text)
    except Exception:
        logger.warning(f"Failed to parse decimal value: {value}")
        return Decimal("0")


def _normalize_tax_id(raw_value: Any, fallback_seed: str) -> str:
    """
    Normalize CPF/CNPJ/document value to fit Client.cpf_cnpj (varchar(20)).

    Preference order:
    1) Valid CPF/CNPJ digits (11/14)
    2) Digits-only version up to 20 chars
    3) Sanitized alphanumeric document up to 20 chars
    4) Deterministic placeholder from fallback seed (always <=20)
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

    digest = hashlib.sha1(fallback_seed.encode("utf-8")).hexdigest()[:17]
    return f"CA-{digest}"


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

    if isinstance(date_value, datetime):
        return date_value.date()
    if isinstance(date_value, date):
        return date_value

    if isinstance(date_value, str):
        text = date_value.strip()
        if not text:
            return None

        date_token = text[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_token, fmt).date()
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            logger.warning(f"Failed to parse date value: {date_value}")
            return None

    return None


async def get_financial_sync_status() -> Dict[str, Any]:
    """
    Get current financial synchronization status and aggregate counters.

    Returns:
        Dict containing:
            - total_records: total financial records in database
            - synced_records: records with Conta Azul linkage and sync timestamp
            - receivable_records: total records of type receivable
            - payable_records: total records of type payable
            - overdue_records: total records currently marked overdue
            - last_sync_time: most recent last_synced_at timestamp (or None)
            - timestamp: status generation timestamp
    """
    db: Session = SessionLocal()
    try:
        total_records = db.query(FinancialRecord).count()
        synced_records = db.query(FinancialRecord).filter(
            FinancialRecord.conta_azul_id.isnot(None),
            FinancialRecord.last_synced_at.isnot(None),
        ).count()
        receivable_records = db.query(FinancialRecord).filter(
            FinancialRecord.transaction_type == "receivable"
        ).count()
        payable_records = db.query(FinancialRecord).filter(
            FinancialRecord.transaction_type == "payable"
        ).count()
        overdue_records = db.query(FinancialRecord).filter(
            FinancialRecord.status == "overdue"
        ).count()

        last_synced = db.query(FinancialRecord).filter(
            FinancialRecord.last_synced_at.isnot(None)
        ).order_by(FinancialRecord.last_synced_at.desc()).first()
        last_sync_time = last_synced.last_synced_at.isoformat() if last_synced else None

        return {
            "total_records": total_records,
            "synced_records": synced_records,
            "receivable_records": receivable_records,
            "payable_records": payable_records,
            "overdue_records": overdue_records,
            "last_sync_time": last_sync_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        db.close()
