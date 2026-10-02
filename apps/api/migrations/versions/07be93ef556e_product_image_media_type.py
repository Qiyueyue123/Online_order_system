"""product image media type

Revision ID: 07be93ef556e
Revises: 3c9f0e2a7b81
Create Date: 2026-07-10 03:56:22.323783
"""

import sqlalchemy as sa
from alembic import op

revision = "07be93ef556e"
down_revision = "3c9f0e2a7b81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column("media_type", sa.String(length=10), server_default="image", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("product_images", "media_type")
