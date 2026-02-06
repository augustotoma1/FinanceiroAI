"""
Dashboard API Endpoints

This module provides FastAPI endpoints for dashboard metrics and monitoring.
Aggregates data from clients, contracts, signatures, and financial records
to provide real-time KPIs for financial oversight and system monitoring.

Endpoints:
- GET /metrics - Get comprehensive dashboard metrics and KPIs
"""

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime
from typing import Dict, Any
import logging

from app.database import get_db
from app.models.client import Client
from app.models.contract import Contract
from app.models.signature import Signature
from app.models.financial_record import FinancialRecord

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


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
            "recent_contracts": recent_contracts,
            "generated_at": datetime.utcnow().isoformat()
        }

        logger.info("Dashboard metrics generated successfully")
        return metrics

    except Exception as e:
        logger.error(f"Error generating dashboard metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate dashboard metrics"
        )
