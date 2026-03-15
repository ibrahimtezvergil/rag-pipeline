"""add chunk content hash"""

from alembic import op
import sqlalchemy as sa


revision = "002_add_chunk_content_hash"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_chunks", sa.Column("content_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rag_chunks", "content_hash")
