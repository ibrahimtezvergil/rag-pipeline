"""merge divergent heads"""

from alembic import op


revision = "004_merge_heads"
down_revision = ("002_add_rag_schedules", "003_add_chunk_content")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
