"""
Dashboard API Endpoints

This module provides FastAPI endpoints for dashboard metrics and monitoring.
Aggregates data from clients, contracts, signatures, and financial records
to provide real-time KPIs for financial oversight and system monitoring.

Endpoints:
- GET /metrics - Get comprehensive dashboard metrics and KPIs
- GET /cash-risk - Get executive cash-risk snapshot with daily history
- GET /financial-sync-status - Get financial synchronization freshness/status
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timezone
from typing import Dict, Any
import logging

from app.database import get_db
from app.config import settings
from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.models.financial_record import FinancialRecord
from app.services.contract_lifecycle_service import build_contract_lifecycle_snapshot
from app.services.cash_risk_service import (
    CashRiskAuthError,
    CashRiskError,
    get_cash_risk_dashboard_data,
)
from app.services.ai_phase2_service import get_phase2_readiness_snapshot
from app.agents.orchestrator import AIEmployeeOrchestrator
from app.background.sync_financial import get_financial_sync_status

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


def _compute_financial_sync_metrics(db: Session) -> Dict[str, Any]:
    """Compute financial synchronization aggregates for dashboard cards."""
    total_records = db.query(func.count(FinancialRecord.id)).scalar() or 0
    synced_records = db.query(func.count(FinancialRecord.id)).filter(
        FinancialRecord.conta_azul_id.isnot(None),
        FinancialRecord.last_synced_at.isnot(None),
    ).scalar() or 0
    receivable_records = db.query(func.count(FinancialRecord.id)).filter(
        FinancialRecord.transaction_type == "receivable"
    ).scalar() or 0
    payable_records = db.query(func.count(FinancialRecord.id)).filter(
        FinancialRecord.transaction_type == "payable"
    ).scalar() or 0
    overdue_records = db.query(func.count(FinancialRecord.id)).filter(
        FinancialRecord.status == "overdue"
    ).scalar() or 0

    last_synced = db.query(FinancialRecord).filter(
        FinancialRecord.last_synced_at.isnot(None)
    ).order_by(FinancialRecord.last_synced_at.desc()).first()
    last_sync_time = last_synced.last_synced_at if last_synced else None

    freshness = "unknown"
    if not last_sync_time:
        freshness = "missing"
    else:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - last_sync_time).total_seconds() / 3600.0
        if age_hours > 48:
            freshness = "stale"
        elif age_hours > 24:
            freshness = "warning"
        else:
            freshness = "fresh"

    return {
        "total_records": total_records,
        "synced_records": synced_records,
        "receivable_records": receivable_records,
        "payable_records": payable_records,
        "overdue_records": overdue_records,
        "last_sync_time": last_sync_time.isoformat() if last_sync_time else None,
        "freshness": freshness,
    }


def _compute_client_sync_metrics(db: Session) -> Dict[str, Any]:
    """Compute client synchronization freshness and coverage card."""
    total_clients = db.query(func.count(Client.id)).scalar() or 0
    synced_clients = db.query(func.count(Client.id)).filter(
        Client.conta_azul_id.isnot(None)
    ).scalar() or 0
    local_only_clients = max(total_clients - synced_clients, 0)
    coverage_pct = (synced_clients / total_clients * 100.0) if total_clients > 0 else 0.0

    last_synced = db.query(Client).filter(
        Client.last_synced_at.isnot(None)
    ).order_by(Client.last_synced_at.desc()).first()
    last_sync_time = last_synced.last_synced_at if last_synced else None

    freshness = "missing"
    hours_since_last_sync = None
    if last_sync_time:
        if last_sync_time.tzinfo is None:
            last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
        hours_since_last_sync = max(
            0.0,
            (datetime.now(timezone.utc) - last_sync_time).total_seconds() / 3600.0,
        )
        if hours_since_last_sync > 6:
            freshness = "stale"
        elif hours_since_last_sync > 2:
            freshness = "warning"
        else:
            freshness = "fresh"

    return {
        "total_clients": total_clients,
        "synced_clients": synced_clients,
        "local_only_clients": local_only_clients,
        "coverage_pct": round(coverage_pct, 2),
        "last_sync_time": last_sync_time.isoformat() if last_sync_time else None,
        "hours_since_last_sync": round(hours_since_last_sync, 2) if hours_since_last_sync is not None else None,
        "freshness": freshness,
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_dashboard_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get comprehensive dashboard metrics and KPIs.

    Retrieves aggregated metrics from all system entities to provide
    a real-time overview of the financial automation system status.

    Metrics include:
    - Total counts: clients, contracts, signatures
    - Contract status breakdown: draft, pending_signature, signed, active, etc.
    - Signature status breakdown: pending, signed, declined
    - Financial metrics: total revenue, overdue payments count, overdue amount
    - Recent activity: latest contracts

    Args:
        db: Database session (injected)

    Returns:
        Dict containing all dashboard metrics and KPIs

    Raises:
        HTTPException 500: If database error occurs

    Example:
        GET /api/dashboard/metrics

        Response (200):
        {
            "clients": {
                "total": 45
            },
            "contracts": {
                "total": 32,
                "by_status": {
                    "draft": 2,
                    "pending_signature": 5,
                    "signed": 10,
                    "active": 12,
                    "expired": 2,
                    "cancelled": 1
                }
            },
            "signatures": {
                "total": 48,
                "pending": 8,
                "signed": 38,
                "declined": 2
            },
            "financial": {
                "total_revenue": 125000.00,
                "overdue_count": 5,
                "overdue_amount": 12500.00,
                "pending_count": 8,
                "pending_amount": 25000.00
            },
            "recent_contracts": [
                {
                    "id": 32,
                    "contract_number": "CTR-2024-032",
                    "client_name": "João Silva",
                    "contract_value": 5000.00,
                    "status": "active",
                    "created_at": "2026-02-06T10:30:00Z"
                },
                ...
            ],
            "generated_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        logger.info("Generating dashboard metrics...")

        # CLIENT METRICS
        total_clients = db.query(func.count(Client.id)).scalar() or 0
        logger.debug(f"Total clients: {total_clients}")

        # CONTRACT METRICS
        total_contracts = db.query(func.count(Contract.id)).scalar() or 0

        # Contract breakdown by status
        contract_status_counts = db.query(
            Contract.status,
            func.count(Contract.id)
        ).group_by(Contract.status).all()

        contracts_by_status = {
            status_name: count for status_name, count in contract_status_counts
        }

        logger.debug(f"Total contracts: {total_contracts}, by status: {contracts_by_status}")

        # SIGNATURE METRICS
        total_signatures = db.query(func.count(Signature.id)).scalar() or 0

        # Signature breakdown by status
        pending_signatures = db.query(func.count(Signature.id)).filter(
            Signature.status == "pending"
        ).scalar() or 0

        signed_signatures = db.query(func.count(Signature.id)).filter(
            Signature.status == "signed"
        ).scalar() or 0

        declined_signatures = db.query(func.count(Signature.id)).filter(
            Signature.status == "declined"
        ).scalar() or 0

        logger.debug(
            f"Signatures - Total: {total_signatures}, "
            f"Pending: {pending_signatures}, "
            f"Signed: {signed_signatures}, "
            f"Declined: {declined_signatures}"
        )

        # FINANCIAL METRICS
        # Total revenue (all paid transactions)
        total_revenue = db.query(
            func.coalesce(func.sum(FinancialRecord.amount), 0)
        ).filter(
            FinancialRecord.status == "paid"
        ).scalar() or 0

        # Overdue payments
        overdue_count = db.query(func.count(FinancialRecord.id)).filter(
            FinancialRecord.status == "overdue"
        ).scalar() or 0

        overdue_amount = db.query(
            func.coalesce(func.sum(FinancialRecord.amount), 0)
        ).filter(
            FinancialRecord.status == "overdue"
        ).scalar() or 0

        # Pending payments
        pending_count = db.query(func.count(FinancialRecord.id)).filter(
            FinancialRecord.status == "pending"
        ).scalar() or 0

        pending_amount = db.query(
            func.coalesce(func.sum(FinancialRecord.amount), 0)
        ).filter(
            FinancialRecord.status == "pending"
        ).scalar() or 0

        logger.debug(
            f"Financial - Revenue: {total_revenue}, "
            f"Overdue: {overdue_count} ({overdue_amount}), "
            f"Pending: {pending_count} ({pending_amount})"
        )

        # RECENT ACTIVITY
        # Get last 5 contracts with client information
        recent_contracts_query = db.query(
            Contract.id,
            Contract.contract_number,
            Contract.contract_value,
            Contract.status,
            Contract.created_at,
            Client.name.label("client_name")
        ).join(
            Client, Contract.client_id == Client.id
        ).order_by(
            Contract.created_at.desc()
        ).limit(5).all()

        recent_contracts = [
            {
                "id": contract.id,
                "contract_number": contract.contract_number,
                "client_name": contract.client_name,
                "contract_value": float(contract.contract_value),
                "status": contract.status,
                "created_at": contract.created_at.isoformat() if contract.created_at else None
            }
            for contract in recent_contracts_query
        ]

        logger.debug(f"Retrieved {len(recent_contracts)} recent contracts")
        financial_sync_metrics = _compute_financial_sync_metrics(db)
        client_sync_metrics = _compute_client_sync_metrics(db)
        contract_lifecycle = build_contract_lifecycle_snapshot(
            db,
            days_ahead=int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30)),
        )

        # BUILD RESPONSE
        metrics = {
            "clients": {
                "total": total_clients
            },
            "contracts": {
                "total": total_contracts,
                "by_status": contracts_by_status
            },
            "signatures": {
                "total": total_signatures,
                "pending": pending_signatures,
                "signed": signed_signatures,
                "declined": declined_signatures
            },
            "financial": {
                "total_revenue": float(total_revenue),
                "overdue_count": overdue_count,
                "overdue_amount": float(overdue_amount),
                "pending_count": pending_count,
                "pending_amount": float(pending_amount)
            },
            "client_sync": client_sync_metrics,
            "financial_sync": financial_sync_metrics,
            "contract_lifecycle": {
                "window_days": int(contract_lifecycle.get("window_days") or 30),
                "monitored_total": int(contract_lifecycle.get("monitored_total") or 0),
                "overdue_count": int(contract_lifecycle.get("overdue_count") or 0),
                "expiring_soon_count": int(contract_lifecycle.get("expiring_soon_count") or 0),
                "missing_end_date_count": int(contract_lifecycle.get("missing_end_date_count") or 0),
                "overdue_top": list(contract_lifecycle.get("overdue") or [])[:5],
                "expiring_soon_top": list(contract_lifecycle.get("expiring_soon") or [])[:5],
            },
            "recent_contracts": recent_contracts,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

        logger.info("Dashboard metrics generated successfully")
        return metrics

    except Exception as e:
        logger.error(f"Error generating dashboard metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate dashboard metrics"
        )


@router.get("/cash-risk", status_code=status.HTTP_200_OK)
async def get_cash_risk(
    refresh: bool = Query(False, description="Force live refresh from Conta Azul"),
    history_days: int = Query(30, ge=1, le=180, description="Number of days in history"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get executive cash-risk snapshot and daily history.

    Returns the current snapshot (cached for today unless refresh=true) and
    historical snapshots persisted in the database.
    """
    try:
        return await get_cash_risk_dashboard_data(
            db=db,
            force_refresh=refresh,
            history_days=history_days,
        )
    except CashRiskAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except CashRiskError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute cash risk snapshot: {exc}",
        )
    except Exception as exc:
        logger.error("Error generating cash risk snapshot: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate cash risk snapshot",
        )


@router.get("/financial-sync-status", status_code=status.HTTP_200_OK)
async def dashboard_financial_sync_status() -> Dict[str, Any]:
    """
    Get financial synchronization status and freshness indicators.

    Returns a compact status payload designed for executive dashboards.
    """
    try:
        return await get_financial_sync_status()
    except Exception as exc:
        logger.error("Error generating financial sync status: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate financial sync status",
        )


@router.get("/ai-employee/status", status_code=status.HTTP_200_OK)
async def ai_employee_status() -> Dict[str, Any]:
    """
    Get AI Employee runtime status and feature gates.
    """
    orchestrator = AIEmployeeOrchestrator()
    return orchestrator.runtime_status()


@router.post("/ai-employee/run", status_code=status.HTTP_200_OK)
async def run_ai_employee_cycle(
    force: bool = Query(False, description="Allow run even when AI_EMPLOYEE_ENABLED=false"),
    engine: str | None = Query(
        None,
        description="Optional orchestration engine override (builtin|langgraph|crewai|auto)",
    ),
) -> Dict[str, Any]:
    """
    Execute one AI Employee orchestration cycle on demand.
    """
    orchestrator = AIEmployeeOrchestrator()
    try:
        return await orchestrator.run_daily_operations(
            trigger="api",
            force=force,
            engine_override=engine,
        )
    except Exception as exc:
        logger.error("Error executing AI Employee cycle: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute AI Employee cycle",
        )


@router.get("/ai-employee/phase2-readiness", status_code=status.HTTP_200_OK)
async def ai_employee_phase2_readiness() -> Dict[str, Any]:
    """
    Get rollout readiness snapshot for AI phase 2 levels (validation, communication, decision).
    """
    try:
        return await get_phase2_readiness_snapshot()
    except Exception as exc:
        logger.error("Error generating AI phase2 readiness: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate AI phase2 readiness snapshot",
        )
