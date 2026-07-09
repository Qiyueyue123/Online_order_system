"""drink options, pay-at-pickup payment_method, confirmed order status

Revision ID: 3c9f0e2a7b81
Revises: 7e4b2c9d1a53
Create Date: 2026-07-09 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "3c9f0e2a7b81"
down_revision = "7e4b2c9d1a53"
branch_labels = None
depends_on = None


# Postgres names an inline sa.UniqueConstraint("cart_id", "variant_id") (no
# explicit name given in bd63f1397a66) using its default "<table>_<cols>_key"
# convention.
_CART_ITEMS_UNIQUE = "cart_items_cart_id_variant_id_key"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Postgres enums can't have a value removed, only added; adding is safe to
        # run outside the migration that starts using it (see 2f6a1d9c8b4e for the
        # same pattern with 'REFUNDED').
        op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'CONFIRMED'")
    # SQLite has no native enum type -- SQLAlchemy backs Enum() with a plain VARCHAR
    # there, so no DDL migration is needed for local sqlite dev databases.

    if bind.dialect.name == "postgresql":
        op.add_column("cart_items", sa.Column("options", sa.Text(), nullable=True))
        # Two lines for the same variant with different options are now separate
        # rows, so a single (cart_id, variant_id) unique row no longer holds.
        op.drop_constraint(_CART_ITEMS_UNIQUE, "cart_items", type_="unique")
    else:
        # SQLite has no "drop an unnamed unique constraint" operation; batch mode
        # recreates the table from a target schema instead, so hand it the current
        # ORM table (which already drops the constraint and adds the column) as
        # that target.
        from app.models import CartItem

        with op.batch_alter_table("cart_items", copy_from=CartItem.__table__):
            pass

    op.add_column("order_items", sa.Column("options", sa.Text(), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "payment_method", sa.String(length=20), nullable=False, server_default="online"
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_method")
    op.drop_column("order_items", "options")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_column("cart_items", "options")
        op.create_unique_constraint(_CART_ITEMS_UNIQUE, "cart_items", ["cart_id", "variant_id"])
    else:
        with op.batch_alter_table("cart_items") as batch_op:
            batch_op.drop_column("options")
            batch_op.create_unique_constraint(
                _CART_ITEMS_UNIQUE, ["cart_id", "variant_id"]
            )
    # Postgres does not support removing a value from an existing enum type, so
    # the 'confirmed' member added in upgrade() is intentionally left in place.
