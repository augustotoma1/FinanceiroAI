"""Add oauth_states table

Revision ID: 003_add_oauth_states_table
Revises: 002_add_conversations_table
Create Date: 2026-02-14 16:10:00.000000

Persists OAuth CSRF state tokens in the database so state validation works
across process restarts and multiple workers.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_add_oauth_states_table"
down_revision: Union[str, None] = "002_add_conversations_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create oauth_states table."""
    op.create_table(
        "oauth_states",
        sa.Column(
            "state",
            sa.String(length=128),
            nullable=False,
            comment="One-time OAuth state token",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Expiration timestamp for state token",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="State creation timestamp",
        ),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        op.f("ix_oauth_states_expires_at"),
        "oauth_states",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop oauth_states table."""
    op.drop_index(op.f("ix_oauth_states_expires_at"), table_name="oauth_states")
    op.drop_table("oauth_states")
