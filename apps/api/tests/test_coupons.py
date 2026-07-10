import uuid

from conftest import add_product

from app.models import Coupon, Order

CHECKOUT_ADDRESS = {
    "recipient_name": "Guest",
    "line1": "1 Tea Street",
    "city": "Umea",
    "postal_code": "90325",
    "country_code": "SE",
}


def _checkout(client, coupon_code=None):
    body = {"email": "guest@example.com", "shipping_address": CHECKOUT_ADDRESS}
    if coupon_code is not None:
        body["coupon_code"] = coupon_code
    return client.post("/api/v1/checkout", json=body)


def test_valid_percent_coupon_applies_exact_discount_and_shipping(client, db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    db.add(Coupon(code="TEAOFF10", percent_off=10, active=True))
    db.commit()

    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 2})
    response = _checkout(client, coupon_code="teaoff10")  # lowercase input is normalized to upper
    assert response.status_code == 201

    order = db.get(Order, uuid.UUID(response.json()["order_id"]))

    subtotal = 3200 * 2  # 6400
    discount = subtotal * 10 // 100  # 640
    shipping = 0  # SE pickup, free
    assert order.subtotal_cents == subtotal
    assert order.discount_cents == discount
    assert order.shipping_cents == shipping
    assert order.total_cents == subtotal - discount + shipping


def test_invalid_coupon_code_is_rejected(client, db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 1})

    response = _checkout(client, coupon_code="DOES-NOT-EXIST")
    assert response.status_code == 422


def test_deactivated_coupon_is_rejected(client, db):
    # NOTE: the Coupon model (app/models.py) has no expiry timestamp field, only an
    # `active` boolean flag. There is no way to test a time-based "expired" coupon
    # without an expires_at column; this test exercises the closest equivalent
    # (a coupon that has been deactivated) as the "invalid/expired" case.
    product = add_product(db, stock=5)
    variant = product.variants[0]
    db.add(Coupon(code="OLDCODE", percent_off=20, active=False))
    db.commit()
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 1})

    response = _checkout(client, coupon_code="OLDCODE")
    assert response.status_code == 422


def test_no_coupon_charges_full_price(client, db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 3})

    response = _checkout(client)
    assert response.status_code == 201

    order = db.get(Order, uuid.UUID(response.json()["order_id"]))

    subtotal = 3200 * 3
    shipping = 0
    assert order.discount_cents == 0
    assert order.total_cents == subtotal + shipping


