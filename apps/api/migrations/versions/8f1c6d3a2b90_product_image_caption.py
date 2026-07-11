"""product image caption

Revision ID: 8f1c6d3a2b90
Revises: 1a2b3c4d5e6f
Create Date: 2026-07-11 09:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "8f1c6d3a2b90"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_images", sa.Column("caption", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("product_images", "caption")
