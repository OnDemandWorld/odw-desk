"""Add messages.read_at (read receipts, V1.6 F-4)

Revision ID: c9d8e7f6a5b4
Revises: ec78fe44b67d
Create Date: 2026-08-02 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d8e7f6a5b4'
down_revision: str | None = 'ec78fe44b67d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: ADD COLUMN IF NOT EXISTS keeps re-runs / partially-migrated
    # databases safe. read_at is nullable so existing rows stay "unread".
    op.execute(
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "COMMENT ON COLUMN messages.read_at IS "
        "'When the message was marked read (read receipt, V1.6 F-4); null = unread'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS read_at")
