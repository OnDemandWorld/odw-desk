"""Unique customer channel identifiers (audit #41)

Revision ID: d4e5f6a7b8c9
Revises: a7f3c2d91e05
Create Date: 2026-11-24

The customer resolver's check-then-insert race created duplicate Customer
rows for the same channel identifier (no unique constraint existed, so its
IntegrityError retry path was unreachable). This migration:

1. Merges existing duplicates: conversations are reassigned to the oldest
   customer row per identifier, then the duplicate rows are deleted.
2. Adds partial unique expression indexes per channel so the race resolves
   to a single winner and the resolver's conflict re-read path works.
"""

import sqlalchemy as sa

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "a7f3c2d91e05"
branch_labels = None
depends_on = None

_CHANNELS = ("whatsapp", "webchat", "email")


def upgrade() -> None:
    for channel in _CHANNELS:
        # Merge duplicates onto the oldest row (created_at, id tie-break).
        op.execute(
            sa.text(
                f"""
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY channel_identifiers->>'{channel}'
                               ORDER BY created_at, id
                           ) AS rn,
                           FIRST_VALUE(id) OVER (
                               PARTITION BY channel_identifiers->>'{channel}'
                               ORDER BY created_at, id
                           ) AS keeper_id
                    FROM customers
                    WHERE channel_identifiers ? '{channel}'
                )
                UPDATE conversations c
                SET customer_id = r.keeper_id
                FROM ranked r
                WHERE c.customer_id = r.id AND r.rn > 1
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY channel_identifiers->>'{channel}'
                               ORDER BY created_at, id
                           ) AS rn
                    FROM customers
                    WHERE channel_identifiers ? '{channel}'
                )
                DELETE FROM customers WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
                """
            )
        )
        op.create_index(
            f"uq_customers_{channel}_identifier",
            "customers",
            [sa.text(f"(channel_identifiers->>'{channel}')")],
            unique=True,
            postgresql_where=sa.text(f"channel_identifiers ? '{channel}'"),
        )


def downgrade() -> None:
    for channel in _CHANNELS:
        op.drop_index(f"uq_customers_{channel}_identifier", table_name="customers")
