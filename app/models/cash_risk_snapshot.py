"""
Cash Risk Snapshot Model

Stores daily executive cash-risk snapshots used by CFO dashboards and reports.
"""

from sqlalchemy import Column, Integer, Date, DateTime, String, Numeric, Text
from sqlalchemy.sql import func

from app.database import Base


class CashRiskSnapshot(Base):
    """Daily snapshot of cash risk, projection and concentration KPIs."""

    __tablename__ = "cash_risk_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, unique=True, index=True)

    saldo_total = Column(Numeric(15, 2), nullable=False, default=0)
    receber_15 = Column(Numeric(15, 2), nullable=False, default=0)
    pagar_15 = Column(Numeric(15, 2), nullable=False, default=0)
    projected_15d = Column(Numeric(15, 2), nullable=False, default=0)

    top3_concentration_pct = Column(Numeric(6, 2), nullable=False, default=0)
    risk_score = Column(Numeric(6, 2), nullable=False, default=0)
    risk_level = Column(String(16), nullable=False, default="medio")
    risk_emoji = Column(String(8), nullable=False, default="🟡")
    recommendation = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

