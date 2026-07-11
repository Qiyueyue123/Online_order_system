"""product options config

Revision ID: 9a4e2f7c1d63
Revises: 8f1c6d3a2b90
Create Date: 2026-07-11 10:00:00.000000
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "9a4e2f7c1d63"
down_revision = "8f1c6d3a2b90"
branch_labels = None
depends_on = None

# The exact hardcoded option groups drinks used before options became
# admin-configurable -- backfilled onto every existing drinks product so
# pricing/labels/behaviour don't change the moment this migration runs.
DRINKS_OPTIONS_CONFIG = [
    {
        "key": "matcha_g",
        "label": "Matcha",
        "choices": [
            {"value": "4", "label": "4 g (standard)", "surcharge_cents": 0, "default": True},
            {
                "value": "6",
                "label": "6 g stronger (+15 kr)",
                "surcharge_cents": 1500,
                "default": False,
            },
        ],
    },
    {
        "key": "whisk",
        "label": "Whisked with",
        "choices": [
            {"value": "water", "label": "Water (standard)", "surcharge_cents": 0, "default": True},
            {
                "value": "oat",
                "label": "Oat milk (frothier)",
                "surcharge_cents": 0,
                "default": False,
            },
        ],
    },
    {
        "key": "base_milk",
        "label": "Base milk",
        "choices": [
            {
                "value": "cow",
                "label": "Cow's milk (standard)",
                "surcharge_cents": 0,
                "default": True,
            },
            {"value": "oat", "label": "Oat milk", "surcharge_cents": 0, "default": False},
        ],
    },
    {
        "key": "milk_ml",
        "label": "Milk amount",
        "choices": [
            {
                "value": "130",
                "label": "130 ml (standard)",
                "surcharge_cents": 0,
                "default": True,
            },
            {
                "value": "160",
                "label": "160 ml (milkier)",
                "surcharge_cents": 0,
                "default": False,
            },
        ],
    },
    {
        "key": "sugar_g",
        "label": "Sugar",
        "choices": [
            {"value": "2", "label": "2 g", "surcharge_cents": 0, "default": False},
            {"value": "4", "label": "4 g (standard)", "surcharge_cents": 0, "default": True},
            {"value": "6", "label": "6 g", "surcharge_cents": 0, "default": False},
            {"value": "8", "label": "8 g", "surcharge_cents": 0, "default": False},
        ],
    },
]


def upgrade() -> None:
    op.add_column("products", sa.Column("options_config", sa.Text(), nullable=True))
    op.add_column("cart_items", sa.Column("options_label", sa.Text(), nullable=True))
    op.add_column("order_items", sa.Column("options_label", sa.Text(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE products SET options_config = :config
            WHERE category_id IN (SELECT id FROM categories WHERE slug = 'drinks')
            """
        ),
        {"config": json.dumps(DRINKS_OPTIONS_CONFIG)},
    )


def downgrade() -> None:
    op.drop_column("order_items", "options_label")
    op.drop_column("cart_items", "options_label")
    op.drop_column("products", "options_config")
