"""rename price_sgd_cents to price_cents, SGD -> SEK defaults

Renaming the column via ALTER TABLE ... RENAME COLUMN is sufficient on
Postgres: the existing CHECK constraint tracks the column by attnum, so
its definition is reported with the new name automatically and does not
need to be dropped or recreated.

Revision ID: 9a1d3e7c5f02
Revises: 2f6a1d9c8b4e
Create Date: 2026-07-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "9a1d3e7c5f02"
down_revision = "2f6a1d9c8b4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("variants", "price_sgd_cents", new_column_name="price_cents")
    op.alter_column(
        "orders", "currency", existing_type=sa.String(length=3), server_default="SEK"
    )
    op.alter_column(
        "payments", "currency", existing_type=sa.String(length=3), server_default="SEK"
    )


def downgrade() -> None:
    op.alter_column(
        "payments", "currency", existing_type=sa.String(length=3), server_default="SGD"
    )
    op.alter_column(
        "orders", "currency", existing_type=sa.String(length=3), server_default="SGD"
    )
    op.alter_column("variants", "price_cents", new_column_name="price_sgd_cents")
