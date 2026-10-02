"""pickup days, order pickup_at, nullable shipping columns

Revision ID: 7e4b2c9d1a53
Revises: 9a1d3e7c5f02
Create Date: 2026-07-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "7e4b2c9d1a53"
down_revision = "9a1d3e7c5f02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pickup_days",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.Integer(), nullable=False),
        sa.Column("slot_capacity", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("slot_minutes > 0"),
        sa.CheckConstraint("slot_capacity > 0"),
        sa.CheckConstraint("start_time < end_time"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pickup_days_date"), "pickup_days", ["date"], unique=True)

    # batch_alter_table so the nullability changes also work on SQLite (table rebuild).
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column("shipping_name", existing_type=sa.String(120), nullable=True)
        batch_op.alter_column("shipping_line1", existing_type=sa.String(200), nullable=True)
        batch_op.alter_column("shipping_city", existing_type=sa.String(120), nullable=True)
        batch_op.alter_column("shipping_postal_code", existing_type=sa.String(32), nullable=True)
        batch_op.alter_column("shipping_country_code", existing_type=sa.String(2), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("shipping_country_code", existing_type=sa.String(2), nullable=False)
        batch_op.alter_column("shipping_postal_code", existing_type=sa.String(32), nullable=False)
        batch_op.alter_column("shipping_city", existing_type=sa.String(120), nullable=False)
        batch_op.alter_column("shipping_line1", existing_type=sa.String(200), nullable=False)
        batch_op.alter_column("shipping_name", existing_type=sa.String(120), nullable=False)
        batch_op.drop_column("pickup_at")

    op.drop_index(op.f("ix_pickup_days_date"), table_name="pickup_days")
    op.drop_table("pickup_days")
