from datetime import UTC, datetime

from test_checkout import add_product

from app.models import (
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from app.services.checkout import expire_order, mark_order_paid


def pending_order(db):
    product = add_product(db, stock=4)
    variant = product.variants[0]
    variant.stock_reserved = 2
    order = Order(
        display_number="M-STATE-1",
        email="guest@example.com",
        status=OrderStatus.PENDING_PAYMENT,
        subtotal_cents=6400,
        shipping_cents=600,
        total_cents=7000,
        shipping_name="Guest",
        shipping_line1="1 Tea Street",
        shipping_city="Singapore",
        shipping_postal_code="018956",
        shipping_country_code="SG",
        reservation_expires_at=datetime.now(UTC),
        items=[
            OrderItem(
                variant_id=variant.id,
                product_name=product.name,
                variant_name=variant.name,
                sku=variant.sku,
                unit_price_cents=3200,
                quantity=2,
            )
        ],
        payment=Payment(status=PaymentStatus.PENDING, amount_cents=7000),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order, variant


def test_payment_consumes_reservation_once(db):
    order, variant = pending_order(db)
    mark_order_paid(db, order)
    db.commit()
    mark_order_paid(db, order)
    db.commit()
    db.refresh(variant)
    assert order.status == OrderStatus.PAID
    assert variant.stock_on_hand == 2
    assert variant.stock_reserved == 0
    assert db.query(InventoryMovement).filter_by(reason="payment_succeeded").count() == 1


def test_expiry_releases_without_consuming_stock(db):
    order, variant = pending_order(db)
    expire_order(db, order)
    db.commit()
    db.refresh(variant)
    assert order.status == OrderStatus.EXPIRED
    assert variant.stock_on_hand == 4
    assert variant.stock_reserved == 0
