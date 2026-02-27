"""
Contract Signature Dispatch Service

Creates and sends a contract PDF to Autentique for electronic signature, then
persists local Contract/Signature state.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.services.autentique_service import AutentiqueAPIError, AutentiqueService
from app.services.contract_generator import (
    ContractGenerator,
    ContractPDFError,
    ContractTemplateError,
    ContractValidationError,
)

logger = logging.getLogger(__name__)

FINAL_CONTRACT_STATUSES = {"cancelled", "expired"}


class ContractSignatureError(Exception):
    """Base error for contract signature dispatch flow."""


class ContractSignatureNotFoundError(ContractSignatureError):
    """Raised when contract/client is missing."""


class ContractSignatureConflictError(ContractSignatureError):
    """Raised when contract cannot be dispatched in current state."""


class ContractSignatureValidationError(ContractSignatureError):
    """Raised when request payload or template data is invalid."""


class ContractSignatureProviderError(ContractSignatureError):
    """Raised when provider call fails."""


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
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _build_template_payload(contract: Contract, client: Client) -> Dict[str, Any]:
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


def _normalize_signers(
    signers: Optional[Sequence[Dict[str, Any]]],
    *,
    fallback_client: Client,
) -> List[Dict[str, str]]:
    if signers:
        source = signers
    else:
        if not _as_text(fallback_client.email):
            raise ContractSignatureValidationError(
                "Contract client has no email; provide signers explicitly."
            )
        source = [
            {
                "name": fallback_client.name,
                "email": fallback_client.email,
                "cpf": fallback_client.cpf_cnpj,
                "action": "SIGN",
            }
        ]

    normalized: List[Dict[str, str]] = []
    seen_emails: set[str] = set()

    for signer in source:
        email = _as_text((signer or {}).get("email")).lower()
        name = _as_text((signer or {}).get("name"))
        cpf = _as_text((signer or {}).get("cpf"))
        action = _as_text((signer or {}).get("action")) or "SIGN"

        if not email:
            raise ContractSignatureValidationError("Signer email is required.")
        if not name:
            name = email
        if email in seen_emails:
            continue

        seen_emails.add(email)
        normalized.append(
            {
                "name": name[:255],
                "email": email[:255],
                "cpf": cpf[:20],
                "action": action[:20],
            }
        )

    if not normalized:
        raise ContractSignatureValidationError("At least one signer is required.")
    return normalized


def _find_local_signature(
    db: Session,
    *,
    contract_id: int,
    autentique_signature_id: str,
    signer_email: str,
) -> Optional[Signature]:
    if autentique_signature_id:
        row = (
            db.query(Signature)
            .filter(
                Signature.contract_id == contract_id,
                Signature.autentique_signature_id == autentique_signature_id,
            )
            .first()
        )
        if row:
            return row

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


def _extract_remote_signatures(
    remote_document: Dict[str, Any],
    *,
    fallback_signers: Sequence[Dict[str, str]],
) -> List[Dict[str, Any]]:
    remote = list(remote_document.get("signatures") or [])
    if remote:
        return remote

    # Defensive fallback for provider responses that omit signatures list.
    return [
        {
            "name": signer.get("name"),
            "email": signer.get("email"),
            "action": signer.get("action", "SIGN"),
            "public_id": None,
            "signed": None,
            "rejected": None,
            "link": {},
        }
        for signer in fallback_signers
    ]


def _upsert_signatures(
    db: Session,
    *,
    contract: Contract,
    remote_document: Dict[str, Any],
    requested_signers: Sequence[Dict[str, str]],
) -> Dict[str, Any]:
    cpf_by_email = {
        signer["email"].lower(): signer["cpf"]
        for signer in requested_signers
        if _as_text(signer.get("cpf"))
    }

    created_signatures = 0
    updated_signatures = 0
    response_signatures: List[Dict[str, Any]] = []
    remote_signatures = _extract_remote_signatures(
        remote_document,
        fallback_signers=requested_signers,
    )

    for idx, remote_sig in enumerate(remote_signatures, start=1):
        remote_sig_id = _as_text(remote_sig.get("public_id"))
        signer_email = _as_text(remote_sig.get("email")).lower()
        signer_name = _as_text(remote_sig.get("name")) or "Assinante"
        action = _as_text(remote_sig.get("action")) or "SIGN"
        short_link = _as_text((remote_sig.get("link") or {}).get("short_link"))

        if remote_sig.get("signed"):
            status = "signed"
        elif remote_sig.get("rejected"):
            status = "declined"
        else:
            status = "pending"

        signed_at = _parse_iso_datetime(remote_sig.get("signed"))
        declined_at = _parse_iso_datetime(remote_sig.get("rejected"))
        signer_cpf = cpf_by_email.get(signer_email)

        local_signature = _find_local_signature(
            db,
            contract_id=int(contract.id),
            autentique_signature_id=remote_sig_id,
            signer_email=signer_email,
        )

        if not local_signature:
            fallback_email = signer_email or f"autentique+{int(contract.id)}-{idx}@local.invalid"
            local_signature = Signature(
                contract_id=int(contract.id),
                signer_name=signer_name[:255],
                signer_email=fallback_email[:255],
                signer_cpf=signer_cpf[:20] if signer_cpf else None,
                status=status,
                autentique_signature_id=remote_sig_id[:100] if remote_sig_id else None,
                signature_token=short_link[:255] if short_link else None,
                signature_method=action[:50] if action else None,
                signed_at=signed_at,
                declined_at=declined_at,
            )
            db.add(local_signature)
            created_signatures += 1
        else:
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
            if signer_cpf and _as_text(local_signature.signer_cpf) != signer_cpf:
                local_signature.signer_cpf = signer_cpf[:20]
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
            if action and _as_text(local_signature.signature_method) != action:
                local_signature.signature_method = action[:50]
                changed = True
            if changed:
                updated_signatures += 1

        response_signatures.append(
            {
                "signer_name": signer_name[:255],
                "signer_email": (signer_email or local_signature.signer_email)[:255],
                "status": status,
                "autentique_signature_id": remote_sig_id[:100] if remote_sig_id else None,
                "signature_token": short_link[:255] if short_link else None,
            }
        )

    return {
        "created_signatures": created_signatures,
        "updated_signatures": updated_signatures,
        "signatures": response_signatures,
    }


async def send_contract_for_signature(
    db: Session,
    *,
    contract_id: int,
    template_name: str = "default_contract.html",
    signers: Optional[Sequence[Dict[str, Any]]] = None,
    show_audit_page: bool = True,
) -> Dict[str, Any]:
    """
    Generate PDF, send to Autentique and persist local signature workflow state.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise ContractSignatureNotFoundError(f"Contract with ID {contract_id} not found")

    client = db.query(Client).filter(Client.id == contract.client_id).first()
    if not client:
        raise ContractSignatureNotFoundError(
            f"Client with ID {contract.client_id} not found for contract {contract_id}"
        )

    if _as_text(contract.autentique_document_id):
        raise ContractSignatureConflictError(
            "Contract already sent for signature."
        )
    if _normalize_status(contract.status) in FINAL_CONTRACT_STATUSES:
        raise ContractSignatureConflictError(
            f"Contract in status '{contract.status}' cannot be sent for signature."
        )

    normalized_signers = _normalize_signers(signers, fallback_client=client)
    template_payload = _build_template_payload(contract, client)

    generator = ContractGenerator()
    try:
        pdf_bytes = await generator.generate_contract_pdf(
            contract_data=template_payload,
            contract_id=contract.contract_number,
            template_name=template_name,
        )
    except (ContractValidationError, ContractTemplateError, ContractPDFError) as exc:
        raise ContractSignatureValidationError(str(exc)) from exc

    signer_payload = [
        {"email": s["email"], "name": s["name"], "action": s["action"]}
        for s in normalized_signers
    ]
    document_name = f"Contrato {contract.contract_number} - {client.name}"
    file_payload = {"base64": base64.b64encode(pdf_bytes).decode("ascii")}

    service = AutentiqueService()
    try:
        created_document = await service.create_document(
            name=document_name,
            file=file_payload,
            signers=signer_payload,
            show_audit_page=bool(show_audit_page),
        )
    except AutentiqueAPIError as exc:
        raise ContractSignatureProviderError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise ContractSignatureProviderError(f"Unexpected provider error: {exc}") from exc

    document_id = _as_text(created_document.get("id"))
    if not document_id:
        raise ContractSignatureProviderError("Autentique response missing document id.")

    existing_document_contract = (
        db.query(Contract)
        .filter(Contract.autentique_document_id == document_id)
        .first()
    )
    if existing_document_contract and int(existing_document_contract.id) != int(contract.id):
        raise ContractSignatureConflictError(
            f"Autentique document {document_id} is already linked to contract {existing_document_contract.id}."
        )

    try:
        with db.begin_nested():
            contract.autentique_document_id = document_id[:100]
            contract.status = "pending_signature"
            contract.signed_at = None
            upsert = _upsert_signatures(
                db,
                contract=contract,
                remote_document=created_document,
                requested_signers=normalized_signers,
            )
        db.commit()
        db.refresh(contract)
    except Exception as exc:
        db.rollback()
        raise ContractSignatureError(f"Failed to persist signature dispatch: {exc}") from exc

    logger.info(
        "Contract %s sent for signature (document_id=%s, created=%s, updated=%s)",
        contract.id,
        contract.autentique_document_id,
        upsert["created_signatures"],
        upsert["updated_signatures"],
    )

    return {
        "contract_id": int(contract.id),
        "contract_number": contract.contract_number,
        "status": contract.status,
        "autentique_document_id": contract.autentique_document_id,
        "template_name": template_name,
        "signers_created": upsert["created_signatures"],
        "signers_updated": upsert["updated_signatures"],
        "signatures": upsert["signatures"],
    }
