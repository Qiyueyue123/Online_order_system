from conftest import ADDRESS, checkout, put_item
from test_admin import admin_headers
from test_pickup import add_drink, add_pickup_day, add_retail, slot_iso

from app.config import get_settings
from app.models import Order, OrderStatus
from app.services.checkout import expire_stale_orders
from app.services.email import _render_order_confirmation


def test_pay_at_pickup_confirms_order_and_consumes_stock_immediately(client, db):
    drink = add_drink(db, stock=10)
    variant = drink.variants[0]
    day = add_pickup_day(db)
    put_item(client, variant, quantity=2)

    response = checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")
    assert response.status_code == 201
    body = response.json()
    assert "/orders/" in body["checkout_url"]
    assert body["reservation_expires_at"] is None

    order = db.query(Order).one()
    assert order.status == OrderStatus.CONFIRMED
    assert order.payment_method == "pay_at_pickup"
    db.refresh(variant)
    # Stock is consumed immediately (not merely reserved): stock_on_hand drops,
    # stock_reserved goes back to zero.
    assert variant.stock_on_hand == 8
    assert variant.stock_reserved == 0


def test_pay_at_pickup_rejected_when_cart_needs_shipping(client, db):
    drink = add_drink(db)
    retail = add_retail(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    put_item(client, retail.variants[0])

    response = checkout(
        client, pickup_at=slot_iso(day), address=ADDRESS, payment_method="pay_at_pickup"
    )
    assert response.status_code == 422


def test_pay_at_pickup_rejected_for_shipping_only_cart(client, db):
    retail = add_retail(db)
    put_item(client, retail.variants[0])

    response = checkout(client, address=ADDRESS, payment_method="pay_at_pickup")
    assert response.status_code == 422


def test_pay_at_pickup_sends_confirmation_email_immediately(client, db, monkeypatch):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])

    sent = []
    import app.api as api_module

    monkeypatch.setattr(
        api_module, "send_order_confirmation", lambda order, s=None: sent.append(order.id)
    )

    response = checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")
    assert response.status_code == 201
    assert len(sent) == 1


def test_pay_at_pickup_email_has_payment_instructions(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")

    order = db.query(Order).one()
    body = _render_order_confirmation(order, get_settings())
    assert "Pay " in body
    assert "at pickup" in body
    assert "cash" in body


def test_pay_at_pickup_email_uses_configured_payment_note(client, db):
    from app.main import app

    settings = get_settings().model_copy(update={"pickup_payment_note": "@ajisai-cafe"})
    app.dependency_overrides[get_settings] = lambda: settings

    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")

    order = db.query(Order).one()
    body = _render_order_confirmation(order, settings)
    assert "Revolut/Swish to @ajisai-cafe" in body


def test_confirmed_order_immune_to_reservation_sweep(client, db):
    drink = add_drink(db, stock=10)
    variant = drink.variants[0]
    day = add_pickup_day(db)
    put_item(client, variant)
    checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")

    count = expire_stale_orders(db)
    assert count == 0
    order = db.query(Order).one()
    assert order.status == OrderStatus.CONFIRMED


def test_admin_can_fulfill_confirmed_order(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")
    order = db.query(Order).one()

    headers = admin_headers(client, db)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "fulfilled"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"


def test_admin_cancel_confirmed_order_restocks(client, db):
    drink = add_drink(db, stock=10)
    variant = drink.variants[0]
    day = add_pickup_day(db)
    put_item(client, variant, quantity=3)
    checkout(client, pickup_at=slot_iso(day), payment_method="pay_at_pickup")
    order = db.query(Order).one()
    db.refresh(variant)
    assert variant.stock_on_hand == 7

    headers = admin_headers(client, db)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "cancelled", "note": "cafe closed early"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db.refresh(variant)
    assert variant.stock_on_hand == 10
    assert variant.stock_reserved == 0


def test_default_payment_method_is_online(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 201

    order = db.query(Order).one()
    assert order.payment_method == "online"
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.reservation_expires_at is not None
