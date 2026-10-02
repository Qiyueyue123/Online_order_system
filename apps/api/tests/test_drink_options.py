import json

from conftest import checkout, put_item
from test_pickup import add_drink, add_pickup_day, slot_iso

from app.models import Order
from app.services.email import _render_order_confirmation

DEFAULT_OPTIONS = {
    "matcha_g": 4,
    "whisk": "water",
    "base_milk": "cow",
    "milk_ml": 130,
    "sugar_g": 4,
}


def test_options_default_to_standard_recipe(client, db):
    drink = add_drink(db)
    put_item(client, drink.variants[0])
    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["options"] == DEFAULT_OPTIONS


def test_options_are_validated(client, db):
    drink = add_drink(db)
    bad_whisk = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "whisk": "almond"},
        },
    )
    assert bad_whisk.status_code == 422

    bad_sugar = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "sugar_g": 5},
        },
    )
    assert bad_sugar.status_code == 422

    bad_matcha_g = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "matcha_g": 5},
        },
    )
    assert bad_matcha_g.status_code == 422

    bad_milk_ml = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "milk_ml": 150},
        },
    )
    assert bad_milk_ml.status_code == 422

    bad_base_milk = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "base_milk": "almond"},
        },
    )
    assert bad_base_milk.status_code == 422

    unknown_key = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {**DEFAULT_OPTIONS, "milk": "oat"},
        },
    )
    assert unknown_key.status_code == 422


def test_same_variant_different_options_are_separate_cart_lines(client, db):
    drink = add_drink(db)
    put_item(client, drink.variants[0], options={**DEFAULT_OPTIONS, "whisk": "water", "sugar_g": 4})
    put_item(client, drink.variants[0], options={**DEFAULT_OPTIONS, "whisk": "oat", "sugar_g": 6})

    cart = client.get("/api/v1/cart").json()
    assert len(cart["items"]) == 2
    options_seen = {tuple(sorted(item["options"].items())) for item in cart["items"]}
    assert len(options_seen) == 2


def test_same_variant_same_options_updates_the_same_line(client, db):
    drink = add_drink(db)
    options = {**DEFAULT_OPTIONS, "whisk": "oat", "sugar_g": 6}
    put_item(client, drink.variants[0], quantity=1, options=options)
    put_item(client, drink.variants[0], quantity=3, options=options)

    cart = client.get("/api/v1/cart").json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 3


def test_options_flow_to_order_item_and_email(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0], options={**DEFAULT_OPTIONS, "whisk": "oat", "sugar_g": 6})

    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 201

    order = db.query(Order).one()
    assert order.items[0].options is not None
    assert json.loads(order.items[0].options) == {**DEFAULT_OPTIONS, "whisk": "oat", "sugar_g": 6}

    email_body = _render_order_confirmation(order)
    assert f"{drink.name} (Iced) x1" in email_body
    assert "4 g matcha, oat whisk, cow milk 130 ml, 6 g sugar" in email_body


def test_6g_matcha_upgrade_adds_surcharge_to_cart_and_order(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    base_price = drink.variants[0].price_cents
    put_item(client, drink.variants[0], options={**DEFAULT_OPTIONS, "matcha_g": 6})

    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["unit_price_cents"] == base_price + 1500
    assert cart["items"][0]["line_total_cents"] == base_price + 1500
    assert cart["subtotal_cents"] == base_price + 1500

    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 201
    order = db.query(Order).one()
    assert order.subtotal_cents == base_price + 1500
    assert order.items[0].unit_price_cents == base_price + 1500


def test_4g_matcha_has_no_surcharge(client, db):
    drink = add_drink(db)
    base_price = drink.variants[0].price_cents
    put_item(client, drink.variants[0], options={**DEFAULT_OPTIONS, "matcha_g": 4})

    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["unit_price_cents"] == base_price
