import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AdminAuditLog,
    Category,
    Order,
    OrderStatus,
    PaymentStatus,
    Product,
    ProductImage,
    Variant,
)
from ..schemas import AdminProductIn, AdminProductUpdateIn
from .checkout import cancel_confirmed_order, cancel_order


def write_audit(
    db: Session,
    *,
    actor_user_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: object,
    detail: dict | None = None,
) -> AdminAuditLog:
    """Record one admin mutation. Callers add this to the same session/transaction
    as the mutation itself and commit once, so the audit row and the change it
    describes are always consistent."""
    row = AdminAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        detail=json.dumps(detail) if detail is not None else None,
    )
    db.add(row)
    return row


def _paginate(db: Session, stmt, *, page: int, page_size: int) -> tuple[list, int]:
    """Run `stmt` (already filtered/ordered) as a page: one count query over the
    same filters, then one offset/limit query for the rows. Shared by
    list_orders_admin and list_audit_log."""
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def list_orders_admin(
    db: Session, *, order_status: OrderStatus | None, page: int, page_size: int
) -> tuple[list[Order], int]:
    conditions = []
    if order_status is not None:
        conditions.append(Order.status == order_status)
    stmt = select(Order).where(*conditions).order_by(Order.created_at.desc())
    return _paginate(db, stmt, page=page, page_size=page_size)


def list_audit_log(db: Session, *, page: int, page_size: int) -> tuple[list[AdminAuditLog], int]:
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    return _paginate(db, stmt, page=page, page_size=page_size)


# Explicit map of allowed order-status transitions. Anything not listed here (including
# no-op "transitions" to the current status) is rejected with 409 by the caller.
def apply_order_transition(db: Session, order: Order, target: OrderStatus) -> None:
    current = order.status
    if current == OrderStatus.PAID and target == OrderStatus.FULFILLED:
        order.status = OrderStatus.FULFILLED
        return
    if current == OrderStatus.PENDING_PAYMENT and target == OrderStatus.CANCELLED:
        cancel_order(db, order)
        return
    if current == OrderStatus.PAID and target == OrderStatus.REFUNDED:
        # Demo-only: this just flips local bookkeeping. A real refund must go through
        # Stripe (stripe.Refund.create against the PaymentIntent/Charge) and only flip
        # local status once Stripe confirms the refund via webhook.
        order.status = OrderStatus.REFUNDED
        order.payment.status = PaymentStatus.REFUNDED
        return
    if current == OrderStatus.CONFIRMED and target == OrderStatus.FULFILLED:
        # Pay-at-pickup: cash/transfer changes hands at the counter, so "fulfilled"
        # here also stands in for "paid" -- there is no separate paid state for it.
        order.status = OrderStatus.FULFILLED
        order.payment.status = PaymentStatus.SUCCEEDED
        return
    if current == OrderStatus.CONFIRMED and target == OrderStatus.CANCELLED:
        cancel_confirmed_order(db, order)
        return
    raise HTTPException(
        status.HTTP_409_CONFLICT, f"Cannot move order from {current.value} to {target.value}"
    )


def create_product(db: Session, data: AdminProductIn) -> Product:
    category = None
    if data.category_slug:
        category = db.scalar(select(Category).where(Category.slug == data.category_slug))
        if category is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    product = Product(
        category=category,
        slug=data.slug,
        name=data.name,
        description=data.description,
        variants=[
            Variant(
                sku=variant.sku,
                name=variant.name,
                weight_grams=variant.weight_grams,
                price_cents=variant.price_cents,
                stock_on_hand=variant.stock_on_hand,
            )
            for variant in data.variants
        ],
        images=[
            ProductImage(url=image.url, alt_text=image.alt_text, position=image.position)
            for image in data.images
        ],
    )
    db.add(product)
    db.flush()
    return product


def _set_if_changed(changes: dict, obj: object, field: str, value: object | None) -> None:
    """If `value` is provided and differs from `obj.field`, record the before/after
    in `changes` and apply it to `obj`. A no-op if `value` is None (field not sent)
    or already equal (field sent unchanged)."""
    if value is not None and value != getattr(obj, field):
        changes[field] = {"from": getattr(obj, field), "to": value}
        setattr(obj, field, value)


def update_product(db: Session, product: Product, data: AdminProductUpdateIn) -> dict:
    changes: dict = {}
    _set_if_changed(changes, product, "name", data.name)
    _set_if_changed(changes, product, "description", data.description)
    _set_if_changed(changes, product, "active", data.active)
    return changes


def update_variant(
    db: Session,
    variant: Variant,
    *,
    price_cents: int | None,
    stock_on_hand: int | None,
    reason: str,
) -> dict:
    from ..models import InventoryMovement

    changes: dict = {}
    _set_if_changed(changes, variant, "price_cents", price_cents)
    if stock_on_hand is not None and stock_on_hand != variant.stock_on_hand:
        if stock_on_hand < variant.stock_reserved:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Stock cannot be below active reservations"
            )
        delta = stock_on_hand - variant.stock_on_hand
        changes["stock_on_hand"] = {"from": variant.stock_on_hand, "to": stock_on_hand}
        variant.stock_on_hand = stock_on_hand
        db.add(
            InventoryMovement(
                variant_id=variant.id,
                quantity_delta=delta,
                reason="admin_adjustment",
                reference=reason,
            )
        )
    return changes
