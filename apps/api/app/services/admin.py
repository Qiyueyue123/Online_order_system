import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    AdminAuditLog,
    CartItem,
    Category,
    Notice,
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    Product,
    ProductImage,
    User,
    Variant,
)
from ..schemas import (
    AdminImageIn,
    AdminImageOrderIn,
    AdminImageUpdateIn,
    AdminNoticeUpdateIn,
    AdminProductIn,
    AdminProductUpdateIn,
)
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


def list_audit_log(
    db: Session, *, page: int, page_size: int
) -> tuple[list[tuple[AdminAuditLog, str]], int]:
    """Each row paired with its actor's display name -- a bare UUID means
    nothing to the café owner reading this log, so we resolve it here with
    one bulk lookup rather than leaving the raw id for the API to render."""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    rows, total = _paginate(db, stmt, page=page, page_size=page_size)
    actor_ids = {row.actor_user_id for row in rows}
    actor_names = (
        dict(db.execute(select(User.id, User.name).where(User.id.in_(actor_ids))).all())
        if actor_ids
        else {}
    )
    annotated = [(row, actor_names.get(row.actor_user_id, "Deleted user")) for row in rows]
    return annotated, total


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
    options_config = (
        json.dumps([group.model_dump() for group in data.options], sort_keys=True)
        if data.options
        else None
    )
    product = Product(
        category=category,
        slug=data.slug,
        name=data.name,
        description=data.description,
        options_config=options_config,
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
    # None means "leave options unchanged" (field not sent); an explicit []
    # clears all option groups -- see AdminProductUpdateIn.options docstring.
    if data.options is not None:
        new_config = (
            json.dumps([group.model_dump() for group in data.options], sort_keys=True)
            if data.options
            else None
        )
        if new_config != product.options_config:
            changes["options"] = {"from": product.options_config, "to": new_config}
            product.options_config = new_config
    return changes


def update_variant(
    db: Session,
    variant: Variant,
    *,
    price_cents: int | None,
    stock_on_hand: int | None,
    active: bool | None = None,
    reason: str,
) -> dict:
    from ..models import InventoryMovement

    changes: dict = {}
    _set_if_changed(changes, variant, "price_cents", price_cents)
    _set_if_changed(changes, variant, "active", active)
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


def add_product_image(db: Session, product: Product, data: AdminImageIn) -> ProductImage:
    image = ProductImage(
        product_id=product.id,
        url=data.url,
        alt_text=data.alt_text,
        caption=data.caption,
        position=data.position,
        media_type=data.media_type,
    )
    db.add(image)
    db.flush()
    return image


def remove_product_image(db: Session, product_id: uuid.UUID, image_id: uuid.UUID) -> None:
    image = db.scalar(
        select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
    )
    if not image:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    db.delete(image)


def get_product_image(db: Session, product_id: uuid.UUID, image_id: uuid.UUID) -> ProductImage:
    image = db.scalar(
        select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
    )
    if not image:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return image


def update_product_image(db: Session, image: ProductImage, data: AdminImageUpdateIn) -> dict:
    changes: dict = {}
    _set_if_changed(changes, image, "alt_text", data.alt_text)
    _set_if_changed(changes, image, "caption", data.caption)
    return changes


def reorder_product_images(db: Session, product: Product, data: AdminImageOrderIn) -> dict:
    """Reassign ProductImage.position from the given ordering. The submitted id
    set must exactly match the product's current images -- a partial list would
    silently orphan the missing images at whatever position they already had,
    and an id from another product would let an admin scramble a listing they
    didn't mean to touch."""
    existing_ids = {image.id for image in product.images}
    submitted_ids = list(data.image_ids)
    if set(submitted_ids) != existing_ids or len(submitted_ids) != len(existing_ids):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "image_ids must contain exactly this product's image ids",
        )
    images_by_id = {image.id: image for image in product.images}
    for index, image_id in enumerate(submitted_ids):
        images_by_id[image_id].position = index
    db.flush()
    return {"image_ids": [str(image_id) for image_id in submitted_ids]}


def delete_product(db: Session, product: Product) -> None:
    """Hard-delete a product. Refuses (409) if any order has ever included one
    of its variants -- that history must stay queryable, so the admin is
    steered to deactivate instead. Cart items are transient and not "history",
    so any referencing this product's variants are deleted first to avoid an
    FK violation (CartItem.variant_id has no ON DELETE CASCADE). Variant/image
    rows cascade via the Product relationships. Uploaded media files are left
    on disk -- an orphaned file is harmless in this local/demo setup and isn't
    worth the risk of deleting the wrong thing."""
    variant_ids = [variant.id for variant in product.variants]
    if variant_ids:
        has_order_history = db.scalar(
            select(OrderItem.id).where(OrderItem.variant_id.in_(variant_ids)).limit(1)
        )
        if has_order_history:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This product has order history — mark it inactive instead.",
            )
        db.execute(delete(CartItem).where(CartItem.variant_id.in_(variant_ids)))
    db.delete(product)
    db.flush()


def update_notice(db: Session, notice: Notice, data: AdminNoticeUpdateIn) -> dict:
    changes: dict = {}
    _set_if_changed(changes, notice, "title", data.title)
    _set_if_changed(changes, notice, "body", data.body)
    _set_if_changed(changes, notice, "active", data.active)
    return changes
