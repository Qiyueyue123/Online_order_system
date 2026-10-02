"""order contact handle

Revision ID: 1a2b3c4d5e6f
Revises: 05635449c5d0
Create Date: 2026-07-10 11:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "1a2b3c4d5e6f"
down_revision = "05635449c5d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("contact_handle", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "contact_handle")
