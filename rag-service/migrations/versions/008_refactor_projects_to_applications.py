"""refactor projects to applications

Revision ID: 008_refactor_projects_to_applications
Revises: 007_add_related_chunk_ids
Create Date: 2026-03-28 00:00:00.000000
"""

from alembic import op


revision = "008_refactor_projects_to_applications"
down_revision = "007_add_related_chunk_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("rag_projects", "rag_applications")
    op.alter_column("rag_documents", "project_id", new_column_name="application_id")
    op.alter_column("rag_schedules", "project_id", new_column_name="application_id")
    op.alter_column("rag_evaluation_runs", "project_id", new_column_name="application_id")
    op.alter_column("rag_chunk_feedback", "project_id", new_column_name="application_id")


def downgrade() -> None:
    op.alter_column("rag_chunk_feedback", "application_id", new_column_name="project_id")
    op.alter_column("rag_evaluation_runs", "application_id", new_column_name="project_id")
    op.alter_column("rag_schedules", "application_id", new_column_name="project_id")
    op.alter_column("rag_documents", "application_id", new_column_name="project_id")
    op.rename_table("rag_applications", "rag_projects")
