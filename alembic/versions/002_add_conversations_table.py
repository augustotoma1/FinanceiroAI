"""Add conversations table

Revision ID: 002_add_conversations_table
Revises: 001_initial_schema
Create Date: 2026-02-13 12:00:00.000000

Adds the conversations table for persisting AI conversation state
in the database, replacing the previous volatile in-memory store.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_conversations_table'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversations table for persistent AI conversation state."""

    op.create_table(
        'conversations',
        sa.Column('id', sa.String(length=36), nullable=False, comment='UUID identifier for the conversation session'),
        sa.Column('messages', sa.JSON(), nullable=False, comment='Array of message objects with role and content fields'),
        sa.Column('complete', sa.Boolean(), nullable=False, server_default='false', comment='Whether conversation has finished data collection'),
        sa.Column('data', sa.JSON(), nullable=True, comment='Extracted structured data from completed conversation'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Conversation start timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last interaction timestamp'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop conversations table."""
    op.drop_table('conversations')
