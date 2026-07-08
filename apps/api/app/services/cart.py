import secrets

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Cart, CartItem, LoginSession, Variant
from ..security import CART_COOKIE, token_hash


def get_or_create_cart(
    db: Session,
    response: Response,
    raw_cart_token: str | None,
    login_session: LoginSession | None,
) -> Cart:
    if login_session:
        cart = db.scalar(
            select(Cart).where(Cart.user_id == login_session.user_id, Cart.checked_out_at.is_(None))
        )
        if cart:
            return cart
    elif raw_cart_token:
        cart = db.scalar(
            select(Cart).where(
                Cart.token_hash == token_hash(raw_cart_token), Cart.checked_out_at.is_(None)
            )
        )
        if cart:
            return cart

    token = secrets.token_urlsafe(32) if not login_session else None
    cart = Cart(
        user_id=login_session.user_id if login_session else None,
        token_hash=token_hash(token) if token else None,
    )
    db.add(cart)
    db.commit()
    db.refresh(cart)
    if token:
        response.set_cookie(
            CART_COOKIE,
            token,
            httponly=True,
            secure=get_settings().cookie_secure,
            samesite="lax",
            max_age=2592000,
        )
    return cart


def set_item(db: Session, cart: Cart, variant_id, quantity: int) -> None:
    variant = db.get(Variant, variant_id)
    if not variant or not variant.active or not variant.product.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    if quantity > variant.available_stock:
        raise HTTPException(status.HTTP_409_CONFLICT, "Requested quantity is unavailable")
    item = db.scalar(
        select(CartItem).where(CartItem.cart_id == cart.id, CartItem.variant_id == variant_id)
    )
    if item:
        item.quantity = quantity
    else:
        db.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=quantity))
    db.commit()


def merge_guest_cart(
    db: Session,
    user_id,
    raw_cart_token: str | None,
) -> None:
    if not raw_cart_token:
        return
    guest_cart = db.scalar(
        select(Cart).where(
            Cart.token_hash == token_hash(raw_cart_token),
            Cart.checked_out_at.is_(None),
            Cart.user_id.is_(None),
        )
    )
    if not guest_cart:
        return
    account_cart = db.scalar(
        select(Cart).where(Cart.user_id == user_id, Cart.checked_out_at.is_(None))
    )
    if not account_cart:
        guest_cart.user_id = user_id
        guest_cart.token_hash = None
        db.commit()
        return
    account_items = {item.variant_id: item for item in account_cart.items}
    # Iterate over a copy: distinct-variant items are removed from guest_cart.items
    # below, which would otherwise mutate the collection while iterating over it.
    for guest_item in list(guest_cart.items):
        existing = account_items.get(guest_item.variant_id)
        if existing:
            existing.quantity = min(
                existing.quantity + guest_item.quantity,
                guest_item.variant.available_stock,
                20,
            )
        else:
            # Re-parent the row by moving it between the relationship collections
            # (not just setting cart_id) so SQLAlchemy's unit-of-work stops
            # considering it an orphan of guest_cart. Cart.items cascades
            # "all, delete-orphan"; a row left in guest_cart.items' loaded
            # collection is deleted along with guest_cart below regardless of
            # its foreign key value.
            guest_cart.items.remove(guest_item)
            account_cart.items.append(guest_item)
    db.delete(guest_cart)
    db.commit()


def cart_payload(cart: Cart) -> dict:
    items = [
        {
            "variant_id": item.variant.id,
            "product_slug": item.variant.product.slug,
            "product_name": item.variant.product.name,
            "variant_name": item.variant.name,
            "sku": item.variant.sku,
            "quantity": item.quantity,
            "unit_price_cents": item.variant.price_cents,
            "line_total_cents": item.quantity * item.variant.price_cents,
        }
        for item in cart.items
    ]
    return {"items": items, "subtotal_cents": sum(item["line_total_cents"] for item in items)}
