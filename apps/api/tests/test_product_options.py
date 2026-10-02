"""Admin-configurable product options: config CRUD/validation, cart
normalisation/pricing against a product's options_config, and email output."""

import uuid

from conftest import checkout, put_item
from test_admin import admin_headers
from test_pickup import add_drink, add_pickup_day, slot_iso

from app.models import Order, Product
from app.services.email import _render_order_confirmation

MATCHA_GROUP = {
    "key": "matcha_g",
    "label": "Matcha",
    "choices": [
        {"value": "4", "label": "4 g (standard)", "surcharge_cents": 0, "default": True},
        {"value": "6", "label": "6 g stronger (+15 kr)", "surcharge_cents": 1500, "default": False},
    ],
}

WHISK_GROUP = {
    "key": "whisk",
    "label": "Whisked with",
    "choices": [
        {"value": "water", "label": "Water (standard)", "surcharge_cents": 0, "default": True},
        {"value": "oat", "label": "Oat milk (frothier)", "surcharge_cents": 0, "default": False},
    ],
}

CONFIGURED_PRODUCT_BODY = {
    "slug": "configurable-latte",
    "name": "Configurable Latte",
    "description": "A drink with admin-editable options",
    "variants": [
        {
            "sku": "CONF-LATTE",
            "name": "Iced",
            "weight_grams": 350,
            "price_cents": 4000,
            "stock_on_hand": 20,
        }
    ],
    "options": [MATCHA_GROUP, WHISK_GROUP],
}


def add_configured_drink(db, options_config):
    """A drinks-category product with a specific options_config, for cart/
    checkout/email tests that need full control over the config shape."""
    import json

    drink = add_drink(db)
    drink.options_config = json.dumps(options_config)
    db.add(drink)
    db.commit()
    db.refresh(drink)
    return drink


# --- Admin CRUD / round-trip -------------------------------------------------


def test_admin_create_product_with_options_round_trips_to_public_get(client, db):
    headers = admin_headers(client, db)
    response = client.post(
        "/api/v1/admin/products", json=CONFIGURED_PRODUCT_BODY, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["options"] == [MATCHA_GROUP, WHISK_GROUP]

    public = client.get(f"/api/v1/products/{CONFIGURED_PRODUCT_BODY['slug']}").json()
    assert public["options"] == [MATCHA_GROUP, WHISK_GROUP]


def test_admin_patch_can_add_a_choice_with_surcharge(client, db):
    headers = admin_headers(client, db)
    create = client.post(
        "/api/v1/admin/products", json=CONFIGURED_PRODUCT_BODY, headers=headers
    )
    product_id = create.json()["id"]

    froth_whisk = {
        **WHISK_GROUP,
        "choices": [
            *WHISK_GROUP["choices"],
            {
                "value": "froth",
                "label": "Frothed milk (+5 kr)",
                "surcharge_cents": 500,
                "default": False,
            },
        ],
    }
    patch = client.patch(
        f"/api/v1/admin/products/{product_id}",
        json={"options": [MATCHA_GROUP, froth_whisk]},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["options"][1]["choices"][-1]["value"] == "froth"

    public = client.get(f"/api/v1/products/{CONFIGURED_PRODUCT_BODY['slug']}").json()
    assert any(choice["value"] == "froth" for choice in public["options"][1]["choices"])


def test_admin_patch_with_empty_options_list_clears_options(client, db):
    headers = admin_headers(client, db)
    create = client.post(
        "/api/v1/admin/products", json=CONFIGURED_PRODUCT_BODY, headers=headers
    )
    product_id = create.json()["id"]

    patch = client.patch(
        f"/api/v1/admin/products/{product_id}", json={"options": []}, headers=headers
    )
    assert patch.status_code == 200
    assert patch.json()["options"] is None

    product = db.get(Product, uuid.UUID(product_id))
    assert product.options_config is None


def test_admin_patch_without_options_field_leaves_options_unchanged(client, db):
    headers = admin_headers(client, db)
    create = client.post(
        "/api/v1/admin/products", json=CONFIGURED_PRODUCT_BODY, headers=headers
    )
    product_id = create.json()["id"]

    patch = client.patch(
        f"/api/v1/admin/products/{product_id}", json={"name": "Renamed Latte"}, headers=headers
    )
    assert patch.status_code == 200
    assert patch.json()["options"] == [MATCHA_GROUP, WHISK_GROUP]


def test_admin_listing_includes_options(client, db):
    headers = admin_headers(client, db)
    client.post("/api/v1/admin/products", json=CONFIGURED_PRODUCT_BODY, headers=headers)
    listing = client.get("/api/v1/admin/products", headers=headers).json()
    slug = CONFIGURED_PRODUCT_BODY["slug"]
    entry = next(item for item in listing["items"] if item["slug"] == slug)
    assert entry["options"] == [MATCHA_GROUP, WHISK_GROUP]


# --- Validation ---------------------------------------------------------------


def _body_with_options(options):
    return {**CONFIGURED_PRODUCT_BODY, "slug": "invalid-options-product", "options": options}


def test_two_defaults_in_a_group_is_rejected(client, db):
    headers = admin_headers(client, db)
    bad_group = {**MATCHA_GROUP, "choices": [
        {**MATCHA_GROUP["choices"][0], "default": True},
        {**MATCHA_GROUP["choices"][1], "default": True},
    ]}
    response = client.post(
        "/api/v1/admin/products", json=_body_with_options([bad_group]), headers=headers
    )
    assert response.status_code == 422


def test_zero_choices_in_a_group_is_rejected(client, db):
    headers = admin_headers(client, db)
    bad_group = {**MATCHA_GROUP, "choices": []}
    response = client.post(
        "/api/v1/admin/products", json=_body_with_options([bad_group]), headers=headers
    )
    assert response.status_code == 422


def test_duplicate_group_keys_are_rejected(client, db):
    headers = admin_headers(client, db)
    response = client.post(
        "/api/v1/admin/products",
        json=_body_with_options([MATCHA_GROUP, MATCHA_GROUP]),
        headers=headers,
    )
    assert response.status_code == 422


def test_bad_key_charset_is_rejected(client, db):
    headers = admin_headers(client, db)
    bad_group = {**MATCHA_GROUP, "key": "Matcha Grams!"}
    response = client.post(
        "/api/v1/admin/products", json=_body_with_options([bad_group]), headers=headers
    )
    assert response.status_code == 422


def test_negative_surcharge_is_rejected(client, db):
    headers = admin_headers(client, db)
    bad_group = {
        **MATCHA_GROUP,
        "choices": [
            {**MATCHA_GROUP["choices"][0]},
            {**MATCHA_GROUP["choices"][1], "surcharge_cents": -100},
        ],
    }
    response = client.post(
        "/api/v1/admin/products", json=_body_with_options([bad_group]), headers=headers
    )
    assert response.status_code == 422


# --- Cart behaviour against a configured product -------------------------------


def test_cart_add_with_valid_options_normalises_and_labels(client, db):
    drink = add_configured_drink(db, [MATCHA_GROUP, WHISK_GROUP])
    put_item(client, drink.variants[0], options={"matcha_g": "6", "whisk": "oat"})

    cart = client.get("/api/v1/cart").json()
    item = cart["items"][0]
    assert item["options"] == {"matcha_g": "6", "whisk": "oat"}
    assert item["options_label"] == "6 g stronger (+15 kr) · Oat milk (frothier)"


def test_cart_add_unknown_key_is_rejected(client, db):
    drink = add_configured_drink(db, [MATCHA_GROUP, WHISK_GROUP])
    response = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {"matcha_g": "4", "sugar_g": "4"},
        },
    )
    assert response.status_code == 422


def test_cart_add_invalid_value_is_rejected(client, db):
    drink = add_configured_drink(db, [MATCHA_GROUP, WHISK_GROUP])
    response = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {"matcha_g": "5"},
        },
    )
    assert response.status_code == 422


def test_cart_add_missing_group_is_defaulted(client, db):
    drink = add_configured_drink(db, [MATCHA_GROUP, WHISK_GROUP])
    put_item(client, drink.variants[0], options={"matcha_g": "6"})

    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["options"] == {"matcha_g": "6", "whisk": "water"}


def test_cart_surcharge_sums_multiple_configured_choices(client, db):
    froth_whisk = {
        **WHISK_GROUP,
        "choices": [
            *WHISK_GROUP["choices"],
            {"value": "froth", "label": "Frothed milk", "surcharge_cents": 500, "default": False},
        ],
    }
    drink = add_configured_drink(db, [MATCHA_GROUP, froth_whisk])
    base_price = drink.variants[0].price_cents
    put_item(client, drink.variants[0], options={"matcha_g": "6", "whisk": "froth"})

    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["unit_price_cents"] == base_price + 2000


def test_product_without_options_config_keeps_legacy_pricing(client, db):
    """add_drink() alone (no options_config) exercises the pre-migration
    legacy path: default-filled DrinkOptionsIn shape, 6g matcha surcharge."""
    drink = add_drink(db)
    base_price = drink.variants[0].price_cents
    put_item(
        client,
        drink.variants[0],
        options={
            "matcha_g": 6,
            "whisk": "water",
            "base_milk": "cow",
            "milk_ml": 130,
            "sugar_g": 4,
        },
    )
    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["unit_price_cents"] == base_price + 1500
    assert cart["items"][0]["options_label"] is None


# --- Email ---------------------------------------------------------------------


def test_email_uses_options_label_when_present(client, db):
    drink = add_configured_drink(db, [MATCHA_GROUP, WHISK_GROUP])
    day = add_pickup_day(db)
    put_item(client, drink.variants[0], options={"matcha_g": "6", "whisk": "oat"})

    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 201

    order = db.query(Order).one()
    assert order.items[0].options_label == "6 g stronger (+15 kr) · Oat milk (frothier)"

    email_body = _render_order_confirmation(order)
    assert "6 g stronger (+15 kr) · Oat milk (frothier)" in email_body
