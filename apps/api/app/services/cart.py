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
    for guest_item in guest_cart.items:
        existing = account_items.get(guest_item.variant_id)
        if existing:
            existing.quantity = min(
                existing.quantity + guest_item.quantity,
                guest_item.variant.available_stock,
                20,
            )
        else:
            guest_item.cart_id = account_cart.id
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
            "unit_price_cents": item.variant.price_sgd_cents,
            "line_total_cents": item.quantity * item.variant.price_sgd_cents,
        }
        for item in cart.items
    ]
    return {"items": items, "subtotal_cents": sum(item["line_total_cents"] for item in items)}
