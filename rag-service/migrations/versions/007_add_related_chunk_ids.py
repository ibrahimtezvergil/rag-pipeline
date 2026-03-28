"""add related chunk ids

Revision ID: 007_add_related_chunk_ids
Revises: 006_add_rag_chunk_feedback
Create Date: 2026-03-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "007_add_related_chunk_ids"
down_revision = "006_add_rag_chunk_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rag_chunks",
        sa.Column("related_chunk_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("rag_chunks", "related_chunk_ids", server_default=None)


def downgrade() -> None:
    op.drop_column("rag_chunks", "related_chunk_ids")
