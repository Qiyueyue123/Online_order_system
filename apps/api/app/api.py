import time
from collections import defaultdict, deque
from datetime import UTC, datetime

import stripe
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import (
    Cart,
    InventoryMovement,
    LoginSession,
    Order,
    ProcessedWebhook,
    Product,
    Role,
    User,
    Variant,
)
from .schemas import (
    AdminStockIn,
    CartItemIn,
    CartOut,
    CheckoutIn,
    CheckoutOut,
    LoginIn,
    OrderOut,
    ProductOut,
    ProductPage,
    RegisterIn,
    SessionOut,
    UserOut,
)
from .security import (
    CART_COOKIE,
    admin_session,
    clear_session_cookie,
    csrf_session,
    current_session,
    hash_password,
    issue_session,
    optional_session,
    token_hash,
    verify_password,
)
from .services.cart import cart_payload, get_or_create_cart, merge_guest_cart, set_item
from .services.catalog import list_products
from .services.checkout import create_pending_order, expire_order, mark_order_paid

router = APIRouter(prefix="/api/v1")
auth_attempts: dict[str, deque[float]] = defaultdict(deque)


def _product_out(product) -> ProductOut:
    return ProductOut(
        id=product.id,
        slug=product.slug,
        name=product.name,
        description=product.description,
        category=product.category.name if product.category else None,
        variants=[
            {
                "id": variant.id,
                "sku": variant.sku,
                "name": variant.name,
                "weight_grams": variant.weight_grams,
                "price_sgd_cents": variant.price_sgd_cents,
                "available_stock": variant.available_stock,
            }
            for variant in product.variants
            if variant.active
        ],
        images=product.images,
    )


@router.get("/products", response_model=ProductPage)
def products(
    q: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=48),
    db: Session = Depends(get_db),
):
    rows, total = list_products(db, query=q, category=category, page=page, page_size=page_size)
    return ProductPage(
        items=[_product_out(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/products/{slug}", response_model=ProductOut)
def product(slug: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Product).where(Product.slug == slug, Product.active.is_(True)))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return _product_out(row)


def _check_auth_rate(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = auth_attempts[key]
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Try again later")
    attempts.append(now)


@router.post("/auth/register", response_model=SessionOut, status_code=201)
def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _check_auth_rate(request)
    user = User(
        email=str(data.email).lower(),
        name=data.name.strip(),
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered") from None
    db.refresh(user)
    merge_guest_cart(db, user.id, cart_token)
    response.delete_cookie(CART_COOKIE)
    session = issue_session(db, user, response, settings)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.post("/auth/login", response_model=SessionOut)
def login(
    data: LoginIn,
    request: Request,
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _check_auth_rate(request)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or not verify_password(user.password_hash, data.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    merge_guest_cart(db, user.id, cart_token)
    response.delete_cookie(CART_COOKIE)
    session = issue_session(db, user, response, settings)
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.get("/auth/session", response_model=SessionOut)
def session_info(session: LoginSession = Depends(current_session)):
    return SessionOut(user=UserOut.model_validate(session.user), csrf_token=session.csrf_token)


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    session: LoginSession = Depends(csrf_session),
    db: Session = Depends(get_db),
):
    session.revoked_at = datetime.now(UTC)
    db.commit()
    clear_session_cookie(response)


def _cart(
    response: Response,
    db: Session,
    cart_token: str | None,
    login_session: LoginSession | None,
) -> Cart:
    return get_or_create_cart(db, response, cart_token, login_session)


@router.get("/cart", response_model=CartOut)
def get_cart(
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    login_session: LoginSession | None = Depends(optional_session),
    db: Session = Depends(get_db),
):
    return cart_payload(_cart(response, db, cart_token, login_session))


@router.put("/cart/items", response_model=CartOut)
def put_cart_item(
    data: CartItemIn,
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    login_session: LoginSession | None = Depends(optional_session),
    db: Session = Depends(get_db),
):
    cart = _cart(response, db, cart_token, login_session)
    set_item(db, cart, data.variant_id, data.quantity)
    db.refresh(cart)
    return cart_payload(cart)


@router.post("/checkout", response_model=CheckoutOut, status_code=201)
def checkout(
    data: CheckoutIn,
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    login_session: LoginSession | None = Depends(optional_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    cart = _cart(response, db, cart_token, login_session)
    try:
        order, guest_token = create_pending_order(db, cart, data, login_session, settings)
    except Exception:
        db.rollback()
        raise
    # Local mode intentionally uses a deterministic demo page. Production creates Stripe Checkout
    # with the order id in metadata; only the signed webhook below can mark the order paid.
    checkout_url = f"{settings.web_origin}/demo-payment/{order.id}"
    if settings.stripe_secret_key.startswith("sk_test_"):
        stripe.api_key = settings.stripe_secret_key
        stripe_session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "sgd",
                        "product_data": {"name": f"Matcha order {order.display_number}"},
                        "unit_amount": order.total_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.web_origin}/orders/{order.id}",
            cancel_url=f"{settings.web_origin}/cart",
            metadata={"order_id": str(order.id)},
            expires_at=int(order.reservation_expires_at.timestamp()),
        )
        order.payment.provider_session_id = stripe_session.id
        db.commit()
        checkout_url = stripe_session.url
    return CheckoutOut(
        order_id=order.id,
        display_number=order.display_number,
        checkout_url=checkout_url,
        guest_lookup_token=guest_token,
        reservation_expires_at=order.reservation_expires_at,
    )


@router.post("/stripe/webhook", status_code=204)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not stripe_signature or not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing webhook signature")
    try:
        event = stripe.Webhook.construct_event(
            await request.body(), stripe_signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook") from error
    if db.get(ProcessedWebhook, event["id"]):
        return
    event_type = event["type"]
    checkout_session = event["data"]["object"]
    order_id = checkout_session.get("metadata", {}).get("order_id")
    order = db.get(Order, order_id) if order_id else None
    if event_type == "checkout.session.completed" and order:
        mark_order_paid(db, order)
    elif event_type == "checkout.session.expired" and order:
        expire_order(db, order)
    db.add(ProcessedWebhook(event_id=event["id"], event_type=event_type))
    db.commit()


@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    session: LoginSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(Order)
            .where(Order.user_id == session.user_id)
            .order_by(Order.created_at.desc())
        ).all()
    )


@router.post("/demo/orders/{order_id}/pay", response_model=OrderOut)
def complete_demo_payment(
    order_id: str,
    lookup_token: str | None = Query(default=None),
    login_session: LoginSession | None = Depends(optional_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.environment != "development" or settings.stripe_secret_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    account_access = login_session and login_session.user_id == order.user_id
    guest_access = lookup_token and order.lookup_token_hash == token_hash(lookup_token)
    if not account_access and not guest_access:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    mark_order_paid(db, order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: str,
    lookup_token: str | None = Query(default=None),
    login_session: LoginSession | None = Depends(optional_session),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    account_access = login_session and (
        login_session.user_id == order.user_id or login_session.user.role == Role.ADMIN
    )
    guest_access = lookup_token and order.lookup_token_hash == token_hash(lookup_token)
    if not account_access and not guest_access:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


@router.patch("/admin/variants/{variant_id}/stock", status_code=204)
def update_stock(
    variant_id: str,
    data: AdminStockIn,
    _: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    variant = db.get(Variant, variant_id)
    if not variant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    if data.stock_on_hand < variant.stock_reserved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Stock cannot be below active reservations")
    delta = data.stock_on_hand - variant.stock_on_hand
    variant.stock_on_hand = data.stock_on_hand
    db.add(
        InventoryMovement(
            variant_id=variant.id,
            quantity_delta=delta,
            reason="admin_adjustment",
            reference=data.reason,
        )
    )
    db.commit()
