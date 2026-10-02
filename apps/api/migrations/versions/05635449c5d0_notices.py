"""notices

Revision ID: 05635449c5d0
Revises: 07be93ef556e
Create Date: 2026-07-10 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "05635449c5d0"
down_revision = "07be93ef556e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notices_active"), "notices", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notices_active"), table_name="notices")
    op.drop_table("notices")
