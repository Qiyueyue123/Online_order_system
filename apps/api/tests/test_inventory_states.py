from conftest import pending_order

from app.models import InventoryMovement, OrderStatus
from app.services.checkout import expire_order, mark_order_paid


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
