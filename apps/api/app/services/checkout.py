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
from .cart import classify_cart
from .pickup import validate_and_lock_slot

# Domestic pickup-origin shipping is free; everywhere else pays one flat
# international rate (no carrier integration yet).
SHIPPING_RATES = {"SE": 0}
INTERNATIONAL_FLAT_RATE_CENTS = 79_00


def create_pending_order(
    db: Session,
    cart: Cart,
    data: CheckoutIn,
    session: LoginSession | None,
    settings: Settings,
) -> tuple[Order, str | None]:
    if not cart.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cart is empty")

    needs_pickup, needs_shipping = classify_cart(cart)
    if needs_pickup and data.pickup_at is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Cart contains drinks; choose a pickup time",
        )
    country = None
    if needs_shipping:
        if data.shipping_address is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Cart contains items to ship; a shipping address is required",
            )
        country = data.shipping_address.country_code.upper()
        # An empty shipping_countries setting means "ship anywhere".
        if settings.shipping_countries and country not in settings.shipping_countries:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Shipping country unsupported"
            )

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
        subtotal += variant.price_cents * item.quantity

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

    # Lock-before-count: takes the PickupDay row lock and holds it until this
    # transaction commits, so competing checkouts can't both grab the last seat.
    pickup_at = validate_and_lock_slot(db, data.pickup_at) if needs_pickup else None

    shipping_cents = 0
    if needs_shipping:
        shipping_cents = SHIPPING_RATES.get(country, INTERNATIONAL_FLAT_RATE_CENTS)

    guest_token = secrets.token_urlsafe(32) if not session else None
    address = data.shipping_address if needs_shipping else None
    order = Order(
        display_number=f"M{datetime.now(UTC):%y%m%d}{secrets.randbelow(100000):05d}",
        user_id=session.user_id if session else None,
        email=str(data.email).lower(),
        lookup_token_hash=token_hash(guest_token) if guest_token else None,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal_cents=subtotal,
        discount_cents=discount,
        shipping_cents=shipping_cents,
        total_cents=subtotal - discount + shipping_cents,
        shipping_name=address.recipient_name if address else None,
        shipping_line1=address.line1 if address else None,
        shipping_line2=address.line2 if address else None,
        shipping_city=address.city if address else None,
        shipping_postal_code=address.postal_code if address else None,
        shipping_country_code=country,
        pickup_at=pickup_at,
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
                unit_price_cents=variant.price_cents,
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


def _release_reservation(db: Session, order: Order, reason: str) -> None:
    """Give back reserved stock for every line item, without touching stock_on_hand.

    Shared by the automatic sweep (expire_order) and admin-initiated cancellation
    (cancel_order) so both paths keep stock_reserved and InventoryMovement bookkeeping
    consistent; only the terminal status and movement `reason` differ.
    """
    for item in order.items:
        variant = db.get(Variant, item.variant_id)
        variant.stock_reserved -= item.quantity
        db.add(
            InventoryMovement(
                variant_id=variant.id,
                quantity_delta=0,
                reserved_delta=-item.quantity,
                reason=reason,
                reference=str(order.id),
            )
        )


def cancel_order(db: Session, order: Order) -> None:
    """Admin-initiated cancellation of a still-pending order (pending_payment -> cancelled)."""
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise ValueError(f"Cannot cancel order in state {order.status}")
    _release_reservation(db, order, "admin_cancelled")
    order.status = OrderStatus.CANCELLED
    order.payment.status = PaymentStatus.FAILED
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
    _release_reservation(db, order, "reservation_expired")
    order.status = OrderStatus.EXPIRED
    order.payment.status = PaymentStatus.FAILED
    order.reservation_expires_at = None
