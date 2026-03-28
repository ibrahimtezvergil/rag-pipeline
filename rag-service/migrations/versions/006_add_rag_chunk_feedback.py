"""add rag chunk feedback

Revision ID: 006_add_rag_chunk_feedback
Revises: 005_add_rag_evaluations
Create Date: 2026-03-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "006_add_rag_chunk_feedback"
down_revision = "005_add_rag_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_chunk_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("query_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["rag_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["rag_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["rag_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_chunk_feedback_project_chunk_created_at",
        "rag_chunk_feedback",
        ["project_id", "chunk_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rag_chunk_feedback_project_chunk_created_at", table_name="rag_chunk_feedback")
    op.drop_table("rag_chunk_feedback")
