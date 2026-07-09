import uuid

from conftest import add_product

from app.config import get_settings
from app.models import Order


def test_checkout_reprices_on_server_and_reserves_stock(client, db):
    product = add_product(db)
    variant = product.variants[0]
    add = client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 2})
    assert add.status_code == 200
    assert add.json()["subtotal_cents"] == 6400

    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Umea",
                "postal_code": "90325",
                "country_code": "SE",
            },
        },
    )
    assert response.status_code == 201
    assert response.json()["guest_lookup_token"]
    db.refresh(variant)
    assert variant.stock_on_hand == 3
    assert variant.stock_reserved == 2


def test_cart_rejects_more_than_available_stock(client, db):
    product = add_product(db, stock=1)
    response = client.put(
        "/api/v1/cart/items",
        json={"variant_id": str(product.variants[0].id), "quantity": 2},
    )
    assert response.status_code == 409


def _place_guest_order(client, db):
    product = add_product(db)
    variant = product.variants[0]
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 1})
    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Umea",
                "postal_code": "90325",
                "country_code": "SE",
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def test_demo_payment_sends_exactly_one_confirmation_email(client, db, monkeypatch):
    from app.main import app

    settings = get_settings().model_copy(update={"environment": "development"})
    app.dependency_overrides[get_settings] = lambda: settings

    order_payload = _place_guest_order(client, db)

    sent = []
    import app.api as api_module

    monkeypatch.setattr(
        api_module, "send_order_confirmation", lambda order, s=None: sent.append(order.id)
    )

    response = client.post(
        f"/api/v1/demo/orders/{order_payload['order_id']}/pay",
        params={"lookup_token": order_payload["guest_lookup_token"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    assert len(sent) == 1

    # A second call is a no-op transition (already paid) and must not resend the email.
    response = client.post(
        f"/api/v1/demo/orders/{order_payload['order_id']}/pay",
        params={"lookup_token": order_payload["guest_lookup_token"]},
    )
    assert response.status_code == 200
    assert len(sent) == 1


def test_any_country_accepted_with_flat_international_rate(client, db):
    # Default shipping_countries is empty, meaning "ship anywhere". Non-SE
    # destinations pay the flat international rate; SE stays free.
    product = add_product(db)
    client.put(
        "/api/v1/cart/items",
        json={"variant_id": str(product.variants[0].id), "quantity": 1},
    )
    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Paris",
                "postal_code": "75001",
                "country_code": "FR",
            },
        },
    )
    assert response.status_code == 201
    order = db.get(Order, uuid.UUID(response.json()["order_id"]))
    assert order.shipping_country_code == "FR"
    assert order.shipping_cents == 7900
    assert order.total_cents == 3200 + 7900


def test_configured_shipping_countries_still_restrict(client, db):
    from app.main import app

    settings = get_settings().model_copy(update={"shipping_countries": ["SE"]})
    app.dependency_overrides[get_settings] = lambda: settings

    product = add_product(db)
    client.put(
        "/api/v1/cart/items",
        json={"variant_id": str(product.variants[0].id), "quantity": 1},
    )
    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Paris",
                "postal_code": "75001",
                "country_code": "FR",
            },
        },
    )
    assert response.status_code == 422
