from test_pickup import add_drink, add_pickup_day, checkout, put_item, slot_iso

from app.models import Order
from app.services.email import _render_order_confirmation


def test_options_default_to_water_and_4g_sugar(client, db):
    drink = add_drink(db)
    put_item(client, drink.variants[0])
    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["options"] == {"whisk": "water", "sugar_g": 4}


def test_options_are_validated(client, db):
    drink = add_drink(db)
    bad_whisk = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {"whisk": "almond", "sugar_g": 4},
        },
    )
    assert bad_whisk.status_code == 422

    bad_sugar = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {"whisk": "oat", "sugar_g": 5},
        },
    )
    assert bad_sugar.status_code == 422

    unknown_key = client.put(
        "/api/v1/cart/items",
        json={
            "variant_id": str(drink.variants[0].id),
            "quantity": 1,
            "options": {"whisk": "oat", "sugar_g": 4, "milk": "oat"},
        },
    )
    assert unknown_key.status_code == 422


def test_same_variant_different_options_are_separate_cart_lines(client, db):
    drink = add_drink(db)
    put_item(client, drink.variants[0], options={"whisk": "water", "sugar_g": 4})
    put_item(client, drink.variants[0], options={"whisk": "oat", "sugar_g": 6})

    cart = client.get("/api/v1/cart").json()
    assert len(cart["items"]) == 2
    options_seen = {tuple(sorted(item["options"].items())) for item in cart["items"]}
    assert options_seen == {
        (("sugar_g", 4), ("whisk", "water")),
        (("sugar_g", 6), ("whisk", "oat")),
    }


def test_same_variant_same_options_updates_the_same_line(client, db):
    drink = add_drink(db)
    put_item(client, drink.variants[0], quantity=1, options={"whisk": "oat", "sugar_g": 6})
    put_item(client, drink.variants[0], quantity=3, options={"whisk": "oat", "sugar_g": 6})

    cart = client.get("/api/v1/cart").json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 3


def test_options_flow_to_order_item_and_email(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0], options={"whisk": "oat", "sugar_g": 6})

    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 201

    order = db.query(Order).one()
    assert order.items[0].options is not None
    body = client.get(
        f"/api/v1/orders/{order.id}",
        params={"lookup_token": response.json()["guest_lookup_token"]},
    ).json()
    assert body["items"][0]["options"] == {"whisk": "oat", "sugar_g": 6}

    email_body = _render_order_confirmation(order)
    assert f"{drink.name} (Iced) x1" in email_body
    assert "oat whisk, 6 g sugar" in email_body
