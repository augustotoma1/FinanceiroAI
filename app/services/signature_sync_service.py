"""
Autentique Signature Sync Service

Synchronizes remote signature status from Autentique documents into local
Signature/Contract records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.signature import Signature
from app.services.autentique_service import AutentiqueAPIError, AutentiqueService

logger = logging.getLogger(__name__)

FINAL_CONTRACT_STATUSES: Set[str] = {"cancelled", "expired"}
SIGNED_SIGNATURE_STATUSES: Set[str] = {"signed"}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_status(value: Any) -> str:
    return _as_text(value).lower()


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    raw = value
    if isinstance(value, dict):
        raw = value.get("created_at")
    text = _as_text(raw)
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_signature_status(remote_signature: Dict[str, Any]) -> str:
    if remote_signature.get("signed"):
        return "signed"
    if remote_signature.get("rejected"):
        return "declined"
    return "pending"


def _sync_contract_signature_status(db: Session, contract_id: int) -> str:
    """
    Recompute contract.status from local signatures.

    Returns resulting normalized contract status.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        return ""

    current_status = _normalize_status(contract.status)
    if current_status in FINAL_CONTRACT_STATUSES:
        return current_status

    signatures = db.query(Signature).filter(Signature.contract_id == contract_id).all()
    if not signatures:
        return current_status

    signature_statuses = [_normalize_status(sig.status) for sig in signatures]
    all_signed = all(status in SIGNED_SIGNATURE_STATUSES for status in signature_statuses)

    if all_signed:
        today = datetime.now(timezone.utc).date()
        target_status = "active" if contract.start_date and contract.start_date <= today else "signed"
        if current_status != target_status:
            contract.status = target_status
        if contract.signed_at is None:
            contract.signed_at = datetime.now(timezone.utc)
        return _normalize_status(contract.status)

    if current_status != "pending_signature":
        contract.status = "pending_signature"
    return _normalize_status(contract.status)


def _find_local_signature(
    db: Session,
    *,
    contract_id: int,
    autentique_signature_id: str,
    signer_email: str,
) -> Optional[Signature]:
    if autentique_signature_id:
        local = (
            db.query(Signature)
            .filter(
                Signature.contract_id == contract_id,
                Signature.autentique_signature_id == autentique_signature_id,
            )
            .first()
        )
        if local:
            return local

    if signer_email:
        return (
            db.query(Signature)
            .filter(
                Signature.contract_id == contract_id,
                Signature.signer_email.ilike(signer_email),
            )
            .first()
        )

    return None


def _reconcile_remote_document(
    db: Session,
    *,
    contract: Contract,
    remote_document: Dict[str, Any],
) -> Dict[str, int]:
    """Apply remote signature payload into local Signature rows for one contract."""
    remote_signatures = list(remote_document.get("signatures") or [])
    created_signatures = 0
    updated_signatures = 0
    updated_contracts = 0
    before_contract_status = _normalize_status(contract.status)

    for idx, remote_signature in enumerate(remote_signatures, start=1):
        remote_sig_id = _as_text(remote_signature.get("public_id"))
        signer_email = _as_text(remote_signature.get("email")).lower()
        signer_name = _as_text(remote_signature.get("name")) or "Assinante"

        local_signature = _find_local_signature(
            db,
            contract_id=int(contract.id),
            autentique_signature_id=remote_sig_id,
            signer_email=signer_email,
        )

        status = _extract_signature_status(remote_signature)
        signed_at = _parse_iso_datetime(remote_signature.get("signed"))
        declined_payload = remote_signature.get("rejected") or {}
        declined_at = _parse_iso_datetime(declined_payload)
        reject_reason = _as_text(declined_payload.get("reason"))
        short_link = _as_text((remote_signature.get("link") or {}).get("short_link"))

        if not local_signature:
            fallback_email = (
                signer_email
                or f"autentique+{int(contract.id)}-{idx}@local.invalid"
            )
            local_signature = Signature(
                contract_id=int(contract.id),
                signer_name=signer_name[:255],
                signer_email=fallback_email[:255],
                status=status,
                autentique_signature_id=remote_sig_id[:100] if remote_sig_id else None,
                signature_token=short_link[:255] if short_link else None,
                signed_at=signed_at,
                declined_at=declined_at,
                notes=reject_reason[:2000] if reject_reason else None,
            )
            db.add(local_signature)
            created_signatures += 1
            continue

        changed = False
        if remote_sig_id and _as_text(local_signature.autentique_signature_id) != remote_sig_id:
            local_signature.autentique_signature_id = remote_sig_id[:100]
            changed = True
        if signer_name and _as_text(local_signature.signer_name) != signer_name:
            local_signature.signer_name = signer_name[:255]
            changed = True
        if signer_email and _as_text(local_signature.signer_email).lower() != signer_email:
            local_signature.signer_email = signer_email[:255]
            changed = True
        if _normalize_status(local_signature.status) != status:
            local_signature.status = status
            changed = True
        if signed_at and local_signature.signed_at != signed_at:
            local_signature.signed_at = signed_at
            changed = True
        if declined_at and local_signature.declined_at != declined_at:
            local_signature.declined_at = declined_at
            changed = True
        if short_link and _as_text(local_signature.signature_token) != short_link:
            local_signature.signature_token = short_link[:255]
            changed = True
        if reject_reason and _as_text(local_signature.notes) != reject_reason:
            local_signature.notes = reject_reason[:2000]
            changed = True
        if changed:
            updated_signatures += 1

    after_contract_status = _sync_contract_signature_status(db, int(contract.id))
    if before_contract_status != after_contract_status:
        updated_contracts += 1

    return {
        "created_signatures": created_signatures,
        "updated_signatures": updated_signatures,
        "updated_contracts": updated_contracts,
    }


async def sync_signatures_for_document(
    db: Session,
    *,
    document_id: str,
) -> Dict[str, Any]:
    """Synchronize local data for one Autentique document ID."""
    normalized_document_id = _as_text(document_id)
    if not normalized_document_id:
        return {
            "success": False,
            "processed_contracts": 0,
            "created_signatures": 0,
            "updated_signatures": 0,
            "updated_contracts": 0,
            "error_count": 1,
            "errors": ["document_id is required"],
        }

    contract = (
        db.query(Contract)
        .filter(Contract.autentique_document_id == normalized_document_id)
        .first()
    )
    if not contract:
        return {
            "success": True,
            "processed_contracts": 0,
            "created_signatures": 0,
            "updated_signatures": 0,
            "updated_contracts": 0,
            "error_count": 0,
            "errors": [],
            "skipped": True,
            "reason": "no local contract for document_id",
            "document_id": normalized_document_id,
        }

    service = AutentiqueService()
    try:
        with db.begin_nested():
            remote_document = await service.get_document_status(document_id=normalized_document_id)
            counters = _reconcile_remote_document(
                db,
                contract=contract,
                remote_document=remote_document,
            )
        db.commit()
        return {
            "success": True,
            "processed_contracts": 1,
            "created_signatures": counters["created_signatures"],
            "updated_signatures": counters["updated_signatures"],
            "updated_contracts": counters["updated_contracts"],
            "error_count": 0,
            "errors": [],
            "document_id": normalized_document_id,
        }
    except Exception as exc:
        logger.error(
            "document %s (contract %s) sync failed: %s",
            normalized_document_id,
            contract.id,
            exc,
            exc_info=True,
        )
        db.rollback()
        return {
            "success": False,
            "processed_contracts": 0,
            "created_signatures": 0,
            "updated_signatures": 0,
            "updated_contracts": 0,
            "error_count": 1,
            "errors": [str(exc)],
            "document_id": normalized_document_id,
        }


async def sync_signatures_from_autentique(
    db: Session,
    *,
    max_contracts: int = 100,
    only_open_contracts: bool = True,
) -> Dict[str, Any]:
    """
    Pull remote signature statuses and reconcile local Signature/Contract records.
    """
    started_at = datetime.now(timezone.utc)
    max_contracts = max(1, int(max_contracts))
    service = AutentiqueService()

    query = db.query(Contract).filter(Contract.autentique_document_id.isnot(None))
    if only_open_contracts:
        query = query.filter(~Contract.status.in_(tuple(FINAL_CONTRACT_STATUSES)))

    contracts = (
        query.order_by(Contract.updated_at.desc(), Contract.id.desc()).limit(max_contracts).all()
    )

    processed_contracts = 0
    created_signatures = 0
    updated_signatures = 0
    updated_contracts = 0
    errors: List[str] = []

    for contract in contracts:
        document_id = _as_text(contract.autentique_document_id)
        if not document_id:
            continue

        try:
            with db.begin_nested():
                remote_document = await service.get_document_status(document_id=document_id)
                counters = _reconcile_remote_document(
                    db,
                    contract=contract,
                    remote_document=remote_document,
                )
                created_signatures += counters["created_signatures"]
                updated_signatures += counters["updated_signatures"]
                updated_contracts += counters["updated_contracts"]
                processed_contracts += 1
        except AutentiqueAPIError as exc:
            error_message = (
                f"document {document_id} (contract {contract.id}) sync failed: {exc}"
            )
            logger.error(error_message)
            errors.append(error_message)
            continue
        except Exception as exc:
            error_message = (
                f"document {document_id} (contract {contract.id}) unexpected error: {exc}"
            )
            logger.error(error_message, exc_info=True)
            errors.append(error_message)
            continue

    db.commit()
    duration_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
    success = len(errors) == 0
    partial_success = processed_contracts > 0 and len(errors) > 0

    return {
        "success": success,
        "partial_success": partial_success,
        "processed_contracts": processed_contracts,
        "created_signatures": created_signatures,
        "updated_signatures": updated_signatures,
        "updated_contracts": updated_contracts,
        "error_count": len(errors),
        "errors": errors,
        "duration_seconds": duration_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "max_contracts": max_contracts,
        "only_open_contracts": only_open_contracts,
    }
