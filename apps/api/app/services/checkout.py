import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    Cart,
    Coupon,
    InventoryMovement,
    LoginSession,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Variant,
)
from ..schemas import CheckoutIn
from ..security import token_hash

SHIPPING_RATES = {"SG": 600, "MY": 1200, "JP": 1800, "AU": 2000, "NZ": 2200}


def create_pending_order(
    db: Session,
    cart: Cart,
    data: CheckoutIn,
    session: LoginSession | None,
    settings: Settings,
) -> tuple[Order, str | None]:
    country = data.shipping_address.country_code.upper()
    if country not in settings.shipping_countries:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Shipping country unsupported")
    if not cart.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cart is empty")

    variant_ids = [item.variant_id for item in cart.items]
    variants = {
        variant.id: variant
        for variant in db.scalars(
            select(Variant).where(Variant.id.in_(variant_ids)).with_for_update()
        ).all()
    }
    subtotal = 0
    for item in cart.items:
        variant = variants[item.variant_id]
        if not variant.active or item.quantity > variant.available_stock:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{variant.sku} is unavailable")
        subtotal += variant.price_sgd_cents * item.quantity

    discount = 0
    if data.coupon_code:
        coupon = db.scalar(
            select(Coupon).where(
                Coupon.code == data.coupon_code.strip().upper(), Coupon.active.is_(True)
            )
        )
        if not coupon:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Coupon is invalid")
        discount = subtotal * coupon.percent_off // 100

    guest_token = secrets.token_urlsafe(32) if not session else None
    address = data.shipping_address
    order = Order(
        display_number=f"M{datetime.now(UTC):%y%m%d}{secrets.randbelow(100000):05d}",
        user_id=session.user_id if session else None,
        email=str(data.email).lower(),
        lookup_token_hash=token_hash(guest_token) if guest_token else None,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal_cents=subtotal,
        discount_cents=discount,
        shipping_cents=SHIPPING_RATES.get(country, 2500),
        total_cents=subtotal - discount + SHIPPING_RATES.get(country, 2500),
        shipping_name=address.recipient_name,
        shipping_line1=address.line1,
        shipping_line2=address.line2,
        shipping_city=address.city,
        shipping_postal_code=address.postal_code,
        shipping_country_code=country,
        reservation_expires_at=datetime.now(UTC) + timedelta(minutes=settings.reservation_minutes),
    )
    db.add(order)
    db.flush()
    for cart_item in cart.items:
        variant = variants[cart_item.variant_id]
        variant.stock_reserved += cart_item.quantity
        db.add(
            OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                product_name=variant.product.name,
                variant_name=variant.name,
                sku=variant.sku,
                unit_price_cents=variant.price_sgd_cents,
                quantity=cart_item.quantity,
            )
        )
        db.add(
            InventoryMovement(
                variant_id=variant.id,
                quantity_delta=0,
                reserved_delta=cart_item.quantity,
                reason="checkout_reserved",
                reference=str(order.id),
            )
        )
    db.add(
        Payment(
            order_id=order.id,
            status=PaymentStatus.PENDING,
            amount_cents=order.total_cents,
        )
    )
    cart.checked_out_at = datetime.now(UTC)
    db.commit()
    db.refresh(order)
    return order, guest_token


def mark_order_paid(db: Session, order: Order) -> None:
    if order.status == OrderStatus.PAID:
        return
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise ValueError(f"Cannot pay order in state {order.status}")
    for item in order.items:
        variant = db.get(Variant, item.variant_id)
        variant.stock_reserved -= item.quantity
        variant.stock_on_hand -= item.quantity
        db.add(
            InventoryMovement(
                variant_id=variant.id,
                quantity_delta=-item.quantity,
                reserved_delta=-item.quantity,
                reason="payment_succeeded",
                reference=str(order.id),
            )
        )
    order.status = OrderStatus.PAID
    order.payment.status = PaymentStatus.SUCCEEDED
    order.reservation_expires_at = None


def expire_stale_orders(db: Session) -> int:
    now = datetime.now(UTC)
    orders = db.scalars(
        select(Order)
        .where(
            Order.status == OrderStatus.PENDING_PAYMENT,
            Order.reservation_expires_at.is_not(None),
            Order.reservation_expires_at <= now,
        )
        .with_for_update()
    ).all()
    expired = 0
    for order in orders:
        expire_order(db, order)
        expired += 1
    db.commit()
    return expired


def expire_order(db: Session, order: Order) -> None:
    if order.status != OrderStatus.PENDING_PAYMENT:
        return
    for item in order.items:
        variant = db.get(Variant, item.variant_id)
        variant.stock_reserved -= item.quantity
        db.add(
            InventoryMovement(
                variant_id=variant.id,
                quantity_delta=0,
                reserved_delta=-item.quantity,
                reason="reservation_expired",
                reference=str(order.id),
            )
        )
    order.status = OrderStatus.EXPIRED
    order.payment.status = PaymentStatus.FAILED
    order.reservation_expires_at = None
