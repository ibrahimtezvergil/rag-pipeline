"""add chunk content"""

from alembic import op
import sqlalchemy as sa


revision = "003_add_chunk_content"
down_revision = "002_add_chunk_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rag_chunks", sa.Column("content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rag_chunks", "content")
