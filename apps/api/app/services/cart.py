import json
import secrets

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Cart, CartItem, LoginSession, Variant
from ..schemas import DrinkOptionsIn
from ..security import CART_COOKIE, token_hash

DRINKS_CATEGORY_SLUG = "drinks"

# The 6 g matcha upgrade is the only option that changes price; 130ml/160ml
# base milk and the whisk/sugar choices are all included at the listed price.
MATCHA_UPGRADE_SURCHARGE_CENTS = 1500


def option_surcharge_cents(raw_options: str | None) -> int:
    """Extra cost on top of variant.price_cents implied by a line's options
    (e.g. the 6 g matcha upgrade). Shared by cart_payload and checkout so the
    two never compute a line's price differently."""
    if not raw_options:
        return 0
    options = json.loads(raw_options)
    return MATCHA_UPGRADE_SURCHARGE_CENTS if options.get("matcha_g") == 6 else 0


def _canonical_options(variant: Variant, options: DrinkOptionsIn | None) -> str | None:
    """Normalise incoming cart-item options to the stable string stored on
    CartItem/OrderItem.options.

    Drinks always get a fully-defaulted options dict (water whisk, 4 g sugar)
    even if the caller sent nothing, so two drink lines can be compared and
    the receipt always has something to print. Non-drink variants carry no
    options at all: whatever the caller sent (if anything) is ignored, since
    there is no concept of "whisk"/"sugar" for a matcha tin.
    """
    is_drink = (
        variant.product is not None
        and variant.product.category is not None
        and variant.product.category.slug == DRINKS_CATEGORY_SLUG
    )
    if not is_drink:
        return None
    normalised = (options or DrinkOptionsIn()).model_dump()
    return json.dumps(normalised, sort_keys=True)


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


def set_item(
    db: Session,
    cart: Cart,
    variant_id,
    quantity: int,
    options: DrinkOptionsIn | None = None,
) -> None:
    variant = db.get(Variant, variant_id)
    if not variant or not variant.active or not variant.product.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    if quantity > variant.available_stock:
        raise HTTPException(status.HTTP_409_CONFLICT, "Requested quantity is unavailable")
    canonical_options = _canonical_options(variant, options)
    # Same variant with different options is a distinct line (e.g. one Iced/oat/6g
    # line and one Iced/water/4g line), so the match key is (variant_id, options)
    # rather than variant_id alone.
    item = db.scalar(
        select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.variant_id == variant_id,
            CartItem.options.is_(canonical_options)
            if canonical_options is None
            else CartItem.options == canonical_options,
        )
    )
    if item:
        item.quantity = quantity
    else:
        db.add(
            CartItem(
                cart_id=cart.id,
                variant_id=variant_id,
                quantity=quantity,
                options=canonical_options,
            )
        )
    db.commit()


def remove_item(db: Session, cart: Cart, item_id) -> None:
    item = db.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id)
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cart item not found")
    db.delete(item)
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
    account_items = {(item.variant_id, item.options): item for item in account_cart.items}
    # Iterate over a copy: distinct-variant items are removed from guest_cart.items
    # below, which would otherwise mutate the collection while iterating over it.
    for guest_item in list(guest_cart.items):
        existing = account_items.get((guest_item.variant_id, guest_item.options))
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


def classify_cart(cart: Cart) -> tuple[bool, bool]:
    """(needs_pickup, needs_shipping): drinks are made at the dorm and picked up,
    everything else ships. A mixed cart needs both."""
    needs_pickup = False
    needs_shipping = False
    for item in cart.items:
        category = item.variant.product.category
        if category is not None and category.slug == DRINKS_CATEGORY_SLUG:
            needs_pickup = True
        else:
            needs_shipping = True
    return needs_pickup, needs_shipping


def cart_payload(cart: Cart) -> dict:
    items = []
    for item in cart.items:
        unit_price_cents = item.variant.price_cents + option_surcharge_cents(item.options)
        items.append(
            {
                "id": item.id,
                "variant_id": item.variant.id,
                "product_slug": item.variant.product.slug,
                "product_name": item.variant.product.name,
                "variant_name": item.variant.name,
                "sku": item.variant.sku,
                "quantity": item.quantity,
                "unit_price_cents": unit_price_cents,
                "line_total_cents": item.quantity * unit_price_cents,
                "options": json.loads(item.options) if item.options else None,
            }
        )
    needs_pickup, needs_shipping = classify_cart(cart)
    return {
        "items": items,
        "subtotal_cents": sum(item["line_total_cents"] for item in items),
        "needs_pickup": needs_pickup,
        "needs_shipping": needs_shipping,
    }
