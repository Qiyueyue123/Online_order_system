import uuid

from test_checkout import add_product

from app.models import Order as OrderModel
from app.services.email import _render_order_confirmation


def _place_order(client, db, email="guest@example.com"):
    product = add_product(db)
    variant = product.variants[0]
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 1})
    response = client.post(
        "/api/v1/checkout",
        json={
            "email": email,
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


def test_track_order_by_display_number_and_email(client, db):
    order = _place_order(client, db, email="tracker@example.com")
    response = client.get(
        "/api/v1/orders/track",
        params={"display_number": order["display_number"], "email": "tracker@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["display_number"] == order["display_number"]


def test_track_order_email_is_case_insensitive(client, db):
    order = _place_order(client, db, email="tracker@example.com")
    response = client.get(
        "/api/v1/orders/track",
        params={"display_number": order["display_number"], "email": "TRACKER@EXAMPLE.COM"},
    )
    assert response.status_code == 200


def test_track_order_wrong_email_is_404(client, db):
    order = _place_order(client, db, email="tracker@example.com")
    response = client.get(
        "/api/v1/orders/track",
        params={"display_number": order["display_number"], "email": "someone-else@example.com"},
    )
    assert response.status_code == 404


def test_track_order_unknown_display_number_is_404(client, db):
    _place_order(client, db, email="tracker@example.com")
    response = client.get(
        "/api/v1/orders/track",
        params={"display_number": "M-NOT-REAL", "email": "tracker@example.com"},
    )
    assert response.status_code == 404


def test_track_order_is_rate_limited(client, db):
    order = _place_order(client, db, email="tracker@example.com")
    for _ in range(10):
        response = client.get(
            "/api/v1/orders/track",
            params={"display_number": order["display_number"], "email": "tracker@example.com"},
        )
        assert response.status_code == 200
    limited = client.get(
        "/api/v1/orders/track",
        params={"display_number": order["display_number"], "email": "tracker@example.com"},
    )
    assert limited.status_code == 429


def test_confirmation_email_includes_tracking_link(client, db):
    order = _place_order(client, db, email="tracker@example.com")
    order_row = db.get(OrderModel, uuid.UUID(order["order_id"]))
    body = _render_order_confirmation(order_row)
    assert "/track?order=" in body
    assert order["display_number"] in body
    assert "tracker%40example.com" in body
