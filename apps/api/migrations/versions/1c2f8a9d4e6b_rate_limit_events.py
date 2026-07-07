"""rate limit events

Revision ID: 1c2f8a9d4e6b
Revises: bd63f1397a66
Create Date: 2026-07-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "1c2f8a9d4e6b"
down_revision = "bd63f1397a66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rate_limit_events_key"), "rate_limit_events", ["key"], unique=False
    )
    op.create_index(
        op.f("ix_rate_limit_events_created_at"),
        "rate_limit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_rate_limit_events_key_created_at",
        "rate_limit_events",
        ["key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_events_key_created_at", table_name="rate_limit_events")
    op.drop_index(op.f("ix_rate_limit_events_created_at"), table_name="rate_limit_events")
    op.drop_index(op.f("ix_rate_limit_events_key"), table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
