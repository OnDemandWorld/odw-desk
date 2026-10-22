"""Add system_settings (admin runtime overrides, D-3/D-4)

Revision ID: a7f3c2d91e05
Revises: c9d8e7f6a5b4
Create Date: 2026-10-22 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a7f3c2d91e05'
down_revision: str | None = 'c9d8e7f6a5b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=100), primary_key=True),
        sa.Column('value', JSONB(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('system_settings')
