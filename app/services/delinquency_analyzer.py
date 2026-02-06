"""
Delinquency Analysis Service

This module provides payment analysis and risk scoring capabilities for identifying
clients at risk of default. Analyzes payment patterns, calculates delinquency risk
scores, and generates alerts for overdue payments.

The service handles:
- Payment history analysis and pattern recognition
- Risk score calculation based on payment behavior
- Overdue payment detection and classification
- Historical payment trend analysis
- Alert generation for high-risk clients

Used for proactive financial risk management and customer relationship monitoring.
Integrates with FinancialRecord model for payment data analysis.

Usage:
    from app.services.delinquency_analyzer import DelinquencyAnalyzer

    analyzer = DelinquencyAnalyzer()

    # Analyze specific client
    risk_report = await analyzer.analyze_client_risk(client_id=123, db=db)
    if risk_report["risk_level"] == "high":
        print(f"High risk client: {risk_report['risk_score']}")

    # Get all overdue payments
    overdue = await analyzer.get_overdue_payments(db=db, days_threshold=30)

    # Batch analysis for all clients
    alerts = await analyzer.analyze_all_clients(db=db)

References:
    - Spec section: Delinquency Analysis (lines 695-706, 819-825)
    - Based on FinancialRecord model fields
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.financial_record import FinancialRecord
from app.models.client import Client

logger = logging.getLogger(__name__)


class DelinquencyAnalyzerError(Exception):
    """Base exception for delinquency analysis errors."""
    pass


class InsufficientDataError(DelinquencyAnalyzerError):
    """Exception raised when insufficient data is available for analysis."""
    pass


class DelinquencyAnalyzer:
    """
    Service for analyzing payment patterns and calculating delinquency risk scores.

    Provides methods for identifying overdue payments, analyzing payment behavior,
    calculating risk scores, and generating alerts for clients at risk of default.

    The analyzer uses rule-based algorithms to evaluate:
    - Payment timeliness (on-time vs. late payments)
    - Payment frequency and consistency
    - Current overdue amounts and age
    - Historical payment patterns
    - Total exposure and transaction volume

    Risk levels are classified as:
    - Low (0-30): Good payment history, no significant issues
    - Medium (31-60): Some delays, requires monitoring
    - High (61-100): Serious delinquency risk, immediate attention needed

    Attributes:
        high_risk_threshold: Risk score threshold for high-risk classification (default: 60)
        medium_risk_threshold: Risk score threshold for medium-risk classification (default: 30)
        critical_days_overdue: Days overdue for critical status (default: 30)
    """

    # Risk score thresholds
    HIGH_RISK_THRESHOLD = 60
    MEDIUM_RISK_THRESHOLD = 30

    # Days overdue thresholds
    CRITICAL_DAYS_OVERDUE = 30
    WARNING_DAYS_OVERDUE = 15

    def __init__(
        self,
        high_risk_threshold: int = HIGH_RISK_THRESHOLD,
        medium_risk_threshold: int = MEDIUM_RISK_THRESHOLD,
        critical_days_overdue: int = CRITICAL_DAYS_OVERDUE
    ):
        """
        Initialize delinquency analyzer with configurable thresholds.

        Args:
            high_risk_threshold: Score threshold for high-risk classification (default: 60)
            medium_risk_threshold: Score threshold for medium-risk classification (default: 30)
            critical_days_overdue: Days threshold for critical overdue status (default: 30)
        """
        self.high_risk_threshold = high_risk_threshold
        self.medium_risk_threshold = medium_risk_threshold
        self.critical_days_overdue = critical_days_overdue

        logger.info(
            f"Delinquency analyzer initialized: "
            f"high_risk={high_risk_threshold}, "
            f"medium_risk={medium_risk_threshold}, "
            f"critical_days={critical_days_overdue}"
        )

    async def analyze_client_risk(
        self,
        client_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Analyze payment risk for a specific client.

        Performs comprehensive risk analysis including:
        - Current overdue payments and amounts
        - Payment history analysis (on-time rate)
        - Average payment delay
        - Total exposure calculation
        - Risk score calculation
        - Risk level classification

        Args:
            client_id: ID of client to analyze
            db: Database session for queries

        Returns:
            Dictionary containing risk analysis results:
                - client_id: Client identifier
                - risk_score: Calculated risk score (0-100)
                - risk_level: Classification (low, medium, high)
                - total_overdue_amount: Sum of overdue payment amounts
                - overdue_count: Number of overdue payments
                - days_overdue_max: Maximum days overdue across all payments
                - on_time_payment_rate: Percentage of on-time payments
                - avg_payment_delay: Average days delayed for late payments
                - total_exposure: Total outstanding amount (pending + overdue)
                - payment_count_total: Total number of payments analyzed
                - last_payment_date: Date of most recent payment
                - recommendations: List of recommended actions

        Raises:
            InsufficientDataError: If client has no financial records
            DelinquencyAnalyzerError: If analysis fails

        Example:
            >>> analyzer = DelinquencyAnalyzer()
            >>> report = await analyzer.analyze_client_risk(client_id=123, db=db)
            >>> print(f"Risk Level: {report['risk_level']}")
            >>> print(f"Risk Score: {report['risk_score']}")
        """
        logger.info(f"Analyzing risk for client_id: {client_id}")

        try:
            # Verify client exists
            client = db.query(Client).filter(Client.id == client_id).first()
            if not client:
                raise DelinquencyAnalyzerError(f"Client not found: {client_id}")

            # Get all financial records for client
            records = db.query(FinancialRecord).filter(
                FinancialRecord.client_id == client_id
            ).all()

            if not records:
                raise InsufficientDataError(
                    f"No financial records found for client_id: {client_id}"
                )

            # Calculate overdue metrics
            overdue_metrics = self._calculate_overdue_metrics(records)

            # Calculate payment behavior metrics
            payment_metrics = self._calculate_payment_metrics(records)

            # Calculate risk score
            risk_score = self._calculate_risk_score(overdue_metrics, payment_metrics)

            # Classify risk level
            risk_level = self._classify_risk_level(risk_score)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                risk_level, overdue_metrics, payment_metrics
            )

            # Compile complete analysis report
            analysis_report = {
                "client_id": client_id,
                "client_name": client.name,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "total_overdue_amount": float(overdue_metrics["total_overdue_amount"]),
                "overdue_count": overdue_metrics["overdue_count"],
                "days_overdue_max": overdue_metrics["days_overdue_max"],
                "on_time_payment_rate": payment_metrics["on_time_rate"],
                "avg_payment_delay": payment_metrics["avg_delay_days"],
                "total_exposure": float(payment_metrics["total_exposure"]),
                "payment_count_total": payment_metrics["total_count"],
                "last_payment_date": payment_metrics["last_payment_date"],
                "recommendations": recommendations,
                "analysis_date": datetime.utcnow().isoformat()
            }

            logger.info(
                f"Risk analysis complete for client_id={client_id}: "
                f"risk_level={risk_level}, risk_score={risk_score}"
            )

            return analysis_report

        except InsufficientDataError:
            raise

        except Exception as e:
            error_msg = f"Failed to analyze client risk for client_id={client_id}: {e}"
            logger.error(error_msg)
            raise DelinquencyAnalyzerError(error_msg)

    async def get_overdue_payments(
        self,
        db: Session,
        days_threshold: int = 1,
        client_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all overdue payments exceeding the threshold.

        Args:
            db: Database session for queries
            days_threshold: Minimum days overdue to include (default: 1)
            client_id: Optional client ID to filter by specific client

        Returns:
            List of overdue payment dictionaries with keys:
                - id, client_id, client_name, transaction_number
                - amount, due_date, days_overdue, status

        Example:
            >>> analyzer = DelinquencyAnalyzer()
            >>> overdue = await analyzer.get_overdue_payments(db, days_threshold=30)
            >>> for payment in overdue:
            ...     print(f"{payment['client_name']}: {payment['days_overdue']} days")
        """
        logger.info(f"Retrieving overdue payments (threshold: {days_threshold} days)")

        try:
            today = date.today()

            # Build query for overdue payments
            query = db.query(FinancialRecord, Client.name).join(
                Client, FinancialRecord.client_id == Client.id
            ).filter(
                and_(
                    FinancialRecord.status.in_(["pending", "overdue"]),
                    FinancialRecord.due_date.isnot(None),
                    FinancialRecord.due_date < today
                )
            )

            # Filter by client if specified
            if client_id:
                query = query.filter(FinancialRecord.client_id == client_id)

            results = query.all()

            # Format results
            overdue_payments = []
            for record, client_name in results:
                days_overdue = (today - record.due_date).days

                if days_overdue >= days_threshold:
                    overdue_payments.append({
                        "id": record.id,
                        "client_id": record.client_id,
                        "client_name": client_name,
                        "transaction_number": record.transaction_number,
                        "transaction_type": record.transaction_type,
                        "amount": float(record.amount),
                        "due_date": record.due_date.isoformat(),
                        "days_overdue": days_overdue,
                        "status": record.status
                    })

            logger.info(f"Found {len(overdue_payments)} overdue payments")
            return overdue_payments

        except Exception as e:
            error_msg = f"Failed to retrieve overdue payments: {e}"
            logger.error(error_msg)
            raise DelinquencyAnalyzerError(error_msg)

    async def analyze_all_clients(
        self,
        db: Session,
        min_risk_level: str = "medium"
    ) -> List[Dict[str, Any]]:
        """
        Analyze all clients and return those meeting minimum risk level.

        Performs batch analysis of all clients with financial records and
        returns those with risk level at or above the specified threshold.

        Args:
            db: Database session for queries
            min_risk_level: Minimum risk level to include - "low", "medium", or "high"
                           (default: "medium")

        Returns:
            List of client risk analysis reports (see analyze_client_risk for structure)
            Sorted by risk_score descending (highest risk first)

        Example:
            >>> analyzer = DelinquencyAnalyzer()
            >>> high_risk_clients = await analyzer.analyze_all_clients(db, min_risk_level="high")
            >>> for client in high_risk_clients:
            ...     print(f"Alert: {client['client_name']} - Risk: {client['risk_score']}")
        """
        logger.info(f"Analyzing all clients (min_risk_level: {min_risk_level})")

        try:
            # Get all clients with financial records
            clients_with_records = db.query(Client.id).join(
                FinancialRecord, Client.id == FinancialRecord.client_id
            ).distinct().all()

            client_ids = [c.id for c in clients_with_records]
            logger.info(f"Found {len(client_ids)} clients with financial records")

            # Analyze each client
            risk_reports = []
            for client_id in client_ids:
                try:
                    report = await self.analyze_client_risk(client_id, db)

                    # Filter by minimum risk level
                    if self._meets_min_risk_level(report["risk_level"], min_risk_level):
                        risk_reports.append(report)

                except InsufficientDataError:
                    logger.warning(f"Skipping client_id={client_id}: insufficient data")
                    continue

            # Sort by risk score (highest first)
            risk_reports.sort(key=lambda x: x["risk_score"], reverse=True)

            logger.info(
                f"Batch analysis complete: {len(risk_reports)} clients "
                f"meet min_risk_level={min_risk_level}"
            )

            return risk_reports

        except Exception as e:
            error_msg = f"Failed to analyze all clients: {e}"
            logger.error(error_msg)
            raise DelinquencyAnalyzerError(error_msg)

    def _calculate_overdue_metrics(self, records: List[FinancialRecord]) -> Dict[str, Any]:
        """Calculate metrics for overdue payments."""
        today = date.today()

        total_overdue_amount = Decimal("0")
        overdue_count = 0
        days_overdue_max = 0

        for record in records:
            # Check if payment is overdue
            if (
                record.status in ["pending", "overdue"] and
                record.due_date and
                record.due_date < today
            ):
                overdue_count += 1
                total_overdue_amount += record.amount
                days_overdue = (today - record.due_date).days
                days_overdue_max = max(days_overdue_max, days_overdue)

        return {
            "total_overdue_amount": total_overdue_amount,
            "overdue_count": overdue_count,
            "days_overdue_max": days_overdue_max
        }

    def _calculate_payment_metrics(self, records: List[FinancialRecord]) -> Dict[str, Any]:
        """Calculate payment behavior metrics."""
        total_count = 0
        on_time_count = 0
        late_count = 0
        total_delay_days = 0
        total_exposure = Decimal("0")
        last_payment_date = None

        for record in records:
            # Only analyze completed payments for behavior metrics
            if record.status == "paid" and record.payment_date and record.due_date:
                total_count += 1

                # Calculate delay
                delay_days = (record.payment_date - record.due_date).days

                if delay_days <= 0:
                    on_time_count += 1
                else:
                    late_count += 1
                    total_delay_days += delay_days

                # Track last payment date
                if not last_payment_date or record.payment_date > last_payment_date:
                    last_payment_date = record.payment_date

            # Calculate total exposure (pending + overdue)
            if record.status in ["pending", "overdue"]:
                total_exposure += record.amount

        # Calculate rates and averages
        on_time_rate = (on_time_count / total_count * 100) if total_count > 0 else 0
        avg_delay_days = (total_delay_days / late_count) if late_count > 0 else 0

        return {
            "total_count": total_count,
            "on_time_count": on_time_count,
            "late_count": late_count,
            "on_time_rate": round(on_time_rate, 2),
            "avg_delay_days": round(avg_delay_days, 2),
            "total_exposure": total_exposure,
            "last_payment_date": last_payment_date.isoformat() if last_payment_date else None
        }

    def _calculate_risk_score(
        self,
        overdue_metrics: Dict[str, Any],
        payment_metrics: Dict[str, Any]
    ) -> int:
        """
        Calculate overall risk score (0-100) based on multiple factors.

        Risk score calculation weights:
        - Days overdue (max 40 points): Critical factor
        - Overdue count (max 20 points): Frequency of issues
        - On-time payment rate (max 30 points): Historical behavior
        - Average payment delay (max 10 points): Typical delay pattern

        Returns:
            Integer risk score between 0 (lowest risk) and 100 (highest risk)
        """
        risk_score = 0

        # Factor 1: Days overdue (max 40 points)
        days_overdue = overdue_metrics["days_overdue_max"]
        if days_overdue > 0:
            # Scale: 0-30 days = 0-20 points, 31-60 = 20-30, 61+ = 30-40
            if days_overdue <= 30:
                risk_score += min(20, days_overdue * 0.67)
            elif days_overdue <= 60:
                risk_score += 20 + min(10, (days_overdue - 30) * 0.33)
            else:
                risk_score += 30 + min(10, (days_overdue - 60) * 0.1)

        # Factor 2: Overdue count (max 20 points)
        overdue_count = overdue_metrics["overdue_count"]
        risk_score += min(20, overdue_count * 5)

        # Factor 3: On-time payment rate (max 30 points - inverse)
        on_time_rate = payment_metrics["on_time_rate"]
        # 100% on-time = 0 points, 0% on-time = 30 points
        risk_score += (100 - on_time_rate) * 0.3

        # Factor 4: Average payment delay (max 10 points)
        avg_delay = payment_metrics["avg_delay_days"]
        risk_score += min(10, avg_delay * 0.5)

        # Ensure score is within bounds
        return int(min(100, max(0, risk_score)))

    def _classify_risk_level(self, risk_score: int) -> str:
        """
        Classify risk level based on risk score.

        Args:
            risk_score: Risk score (0-100)

        Returns:
            Risk level: "low", "medium", or "high"
        """
        if risk_score >= self.high_risk_threshold:
            return "high"
        elif risk_score >= self.medium_risk_threshold:
            return "medium"
        else:
            return "low"

    def _generate_recommendations(
        self,
        risk_level: str,
        overdue_metrics: Dict[str, Any],
        payment_metrics: Dict[str, Any]
    ) -> List[str]:
        """
        Generate actionable recommendations based on risk analysis.

        Args:
            risk_level: Classified risk level
            overdue_metrics: Overdue payment metrics
            payment_metrics: Payment behavior metrics

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if risk_level == "high":
            recommendations.append("⚠️ URGENT: Contact client immediately regarding overdue payments")
            recommendations.append("Consider suspending services until payment is received")
            recommendations.append("Escalate to collections team if no response within 48 hours")

        if overdue_metrics["days_overdue_max"] > self.critical_days_overdue:
            recommendations.append(
                f"Critical: Payment overdue by {overdue_metrics['days_overdue_max']} days"
            )

        if overdue_metrics["overdue_count"] > 1:
            recommendations.append(
                f"Multiple overdue payments ({overdue_metrics['overdue_count']}) - review payment terms"
            )

        if payment_metrics["on_time_rate"] < 50:
            recommendations.append(
                "Poor payment history - consider requiring advance payment or deposits"
            )

        if payment_metrics["avg_delay_days"] > 10:
            recommendations.append(
                f"Average delay of {payment_metrics['avg_delay_days']} days - "
                "discuss payment schedule adjustment"
            )

        if risk_level == "medium":
            recommendations.append("Send payment reminder and monitor closely")
            recommendations.append("Consider implementing automated payment reminders")

        if risk_level == "low" and len(recommendations) == 0:
            recommendations.append("✓ Client in good standing - continue standard monitoring")

        return recommendations

    def _meets_min_risk_level(self, risk_level: str, min_risk_level: str) -> bool:
        """
        Check if risk level meets minimum threshold.

        Args:
            risk_level: Current risk level
            min_risk_level: Minimum risk level threshold

        Returns:
            True if risk_level meets or exceeds min_risk_level
        """
        risk_hierarchy = {"low": 0, "medium": 1, "high": 2}
        return risk_hierarchy[risk_level] >= risk_hierarchy[min_risk_level]
