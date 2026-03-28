"""add rag evaluations tables

Revision ID: 005_add_rag_evaluations
Revises: 004_merge_heads
Create Date: 2026-03-28 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "005_add_rag_evaluations"
down_revision = "004_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("faithfulness_avg", sa.Float(), nullable=True),
        sa.Column("answer_relevancy_avg", sa.Float(), nullable=True),
        sa.Column("context_recall_avg", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_table(
        "rag_evaluation_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_evaluation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("ground_truth", sa.Text(), nullable=False),
        sa.Column("reference_context", sa.Text(), nullable=False),
        sa.Column("model_answer", sa.Text(), nullable=True),
        sa.Column("retrieved_context", sa.Text(), nullable=True),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("answer_relevancy_score", sa.Float(), nullable=True),
        sa.Column("context_recall_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rag_evaluation_samples")
    op.drop_table("rag_evaluation_runs")
