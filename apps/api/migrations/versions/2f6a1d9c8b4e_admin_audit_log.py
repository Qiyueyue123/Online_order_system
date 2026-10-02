"""admin audit log and refunded order status

Revision ID: 2f6a1d9c8b4e
Revises: 1c2f8a9d4e6b
Create Date: 2026-07-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "2f6a1d9c8b4e"
down_revision = "1c2f8a9d4e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Postgres enums can't have a value removed, only added; adding is safe to run
        # outside the migration that will start using it (see downgrade() note below).
        op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'REFUNDED'")
    # SQLite has no native enum type -- SQLAlchemy backs Enum() with a plain VARCHAR
    # there, so no DDL migration is needed for local sqlite dev databases; the new
    # member becomes valid the moment app/models.py is imported.

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_audit_log_actor_user_id"), "admin_audit_log", ["actor_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_admin_audit_log_created_at"), "admin_audit_log", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_log_created_at"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_actor_user_id"), table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    # Postgres does not support removing a value from an existing enum type, so the
    # 'refunded' member added in upgrade() is intentionally left in place.
