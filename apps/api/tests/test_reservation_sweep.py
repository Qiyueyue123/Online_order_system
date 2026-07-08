from datetime import UTC, datetime, timedelta

from test_checkout import add_product

from app.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus
from app.services.checkout import expire_stale_orders


def make_order(db, variant, *, status, reservation_expires_at, quantity=1):
    order = Order(
        display_number=f"M{datetime.now(UTC):%y%m%d%H%M%S%f}",
        email="guest@example.com",
        status=status,
        subtotal_cents=variant.price_cents * quantity,
        shipping_cents=600,
        total_cents=variant.price_cents * quantity + 600,
        shipping_name="Guest",
        shipping_line1="1 Tea Street",
        shipping_city="Umea",
        shipping_postal_code="90325",
        shipping_country_code="SE",
        reservation_expires_at=reservation_expires_at,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            product_name=variant.product.name,
            variant_name=variant.name,
            sku=variant.sku,
            unit_price_cents=variant.price_cents,
            quantity=quantity,
        )
    )
    db.add(
        Payment(
            order_id=order.id,
            status=PaymentStatus.SUCCEEDED if status == OrderStatus.PAID else PaymentStatus.PENDING,
            amount_cents=order.total_cents,
        )
    )
    variant.stock_reserved += quantity
    db.commit()
    db.refresh(order)
    return order


def test_expires_pending_order_past_expiry_and_releases_stock(db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    order = make_order(
        db,
        variant,
        status=OrderStatus.PENDING_PAYMENT,
        reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        quantity=2,
    )

    count = expire_stale_orders(db)

    assert count == 1
    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.EXPIRED
    assert order.reservation_expires_at is None
    assert variant.stock_reserved == 0
    assert order.payment.status == PaymentStatus.FAILED


def test_pending_order_with_future_expiry_is_untouched(db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    order = make_order(
        db,
        variant,
        status=OrderStatus.PENDING_PAYMENT,
        reservation_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        quantity=2,
    )

    count = expire_stale_orders(db)

    assert count == 0
    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.reservation_expires_at is not None
    assert variant.stock_reserved == 2


def test_sweep_is_idempotent_when_run_twice(db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    order = make_order(
        db,
        variant,
        status=OrderStatus.PENDING_PAYMENT,
        reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        quantity=2,
    )

    first = expire_stale_orders(db)
    second = expire_stale_orders(db)

    assert first == 1
    assert second == 0
    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.EXPIRED
    assert variant.stock_reserved == 0


def test_paid_orders_are_never_expired(db):
    product = add_product(db, stock=5)
    variant = product.variants[0]
    order = make_order(
        db,
        variant,
        status=OrderStatus.PAID,
        reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        quantity=2,
    )

    count = expire_stale_orders(db)

    assert count == 0
    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.PAID
    assert variant.stock_reserved == 2
