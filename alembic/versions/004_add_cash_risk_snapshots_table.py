"""Add cash_risk_snapshots table

Revision ID: 004_cash_risk_snapshots
Revises: 003_add_oauth_states_table
Create Date: 2026-02-15 01:20:00.000000

Stores daily cash-risk snapshots for executive monitoring.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_cash_risk_snapshots"
down_revision: Union[str, None] = "003_add_oauth_states_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cash_risk_snapshots table."""
    op.create_table(
        "cash_risk_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("saldo_total", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("receber_15", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("pagar_15", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("projected_15d", sa.Numeric(precision=15, scale=2), nullable=False, server_default="0"),
        sa.Column("top3_concentration_pct", sa.Numeric(precision=6, scale=2), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Numeric(precision=6, scale=2), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="medio"),
        sa.Column("risk_emoji", sa.String(length=8), nullable=False, server_default="🟡"),
        sa.Column("recommendation", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date"),
    )
    op.create_index(
        op.f("ix_cash_risk_snapshots_id"),
        "cash_risk_snapshots",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cash_risk_snapshots_snapshot_date"),
        "cash_risk_snapshots",
        ["snapshot_date"],
        unique=True,
    )


def downgrade() -> None:
    """Drop cash_risk_snapshots table."""
    op.drop_index(op.f("ix_cash_risk_snapshots_snapshot_date"), table_name="cash_risk_snapshots")
    op.drop_index(op.f("ix_cash_risk_snapshots_id"), table_name="cash_risk_snapshots")
    op.drop_table("cash_risk_snapshots")
