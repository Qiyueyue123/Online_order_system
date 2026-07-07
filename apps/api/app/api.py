import json
import logging
import uuid
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
    LoginSession,
    Order,
    OrderStatus,
    ProcessedWebhook,
    Product,
    Role,
    User,
    Variant,
)
from .schemas import (
    AdminOrderOut,
    AdminOrderPage,
    AdminOrderStatusIn,
    AdminProductIn,
    AdminProductUpdateIn,
    AdminStockIn,
    AdminVariantUpdateIn,
    AuditLogOut,
    AuditLogPage,
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
from .services.admin import (
    apply_order_transition,
    create_product,
    list_audit_log,
    list_orders_admin,
    update_product,
    update_variant,
    write_audit,
)
from .services.cart import cart_payload, get_or_create_cart, merge_guest_cart, set_item
from .services.catalog import list_products
from .services.checkout import create_pending_order, expire_order, mark_order_paid
from .services.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

AUTH_RATE_LIMIT = 10
AUTH_RATE_WINDOW_SECONDS = 60


def _parse_uuid(value: str) -> uuid.UUID | None:
    """Best-effort coercion of a path/metadata string into a uuid.UUID.

    SQLAlchemy's Uuid column type needs an actual uuid.UUID instance on
    dialects without native UUID support (e.g. SQLite); passing a plain str
    straight into db.get() raises at the DB layer. Callers should treat a
    None return as "not found" rather than letting a malformed id 500.
    """
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _parse_uuid_or_404(value: str, detail: str) -> uuid.UUID:
    parsed = _parse_uuid(value)
    if parsed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    return parsed


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


def _check_auth_rate(request: Request, db: Session) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"auth:{ip}"
    if not check_rate_limit(db, key, AUTH_RATE_LIMIT, AUTH_RATE_WINDOW_SECONDS):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Try again later")


@router.post("/auth/register", response_model=SessionOut, status_code=201)
def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    cart_token: str | None = Cookie(default=None, alias=CART_COOKIE),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _check_auth_rate(request, db)
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
    _check_auth_rate(request, db)
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
    order = None
    if order_id:
        order_uuid = _parse_uuid(order_id)
        if order_uuid is None:
            logger.warning("stripe webhook metadata order_id is not a valid UUID: %r", order_id)
        else:
            order = db.get(Order, order_uuid)
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
    order = db.get(Order, _parse_uuid_or_404(order_id, "Order not found"))
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
    order = db.get(Order, _parse_uuid_or_404(order_id, "Order not found"))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    account_access = login_session and (
        login_session.user_id == order.user_id or login_session.user.role == Role.ADMIN
    )
    guest_access = lookup_token and order.lookup_token_hash == token_hash(lookup_token)
    if not account_access and not guest_access:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


# --- Admin ---------------------------------------------------------------
#
# Every mutation below is behind admin_session (admin role + CSRF) and writes
# exactly one AdminAuditLog row in the same transaction as the change, so the
# audit trail can never silently drift from what actually happened.


@router.patch("/admin/variants/{variant_id}/stock", status_code=204)
def update_stock(
    variant_id: str,
    data: AdminStockIn,
    session: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    """Legacy stock-only endpoint, kept working so existing callers don't break.

    Superseded by PATCH /admin/variants/{variant_id}, which folds in price
    updates too; new integrations should use that route. This one now shares
    the same update_variant() logic instead of duplicating the stock checks.
    """
    variant = db.get(Variant, _parse_uuid_or_404(variant_id, "Variant not found"))
    if not variant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    changes = update_variant(
        db, variant, price_sgd_cents=None, stock_on_hand=data.stock_on_hand, reason=data.reason
    )
    write_audit(
        db,
        actor_user_id=session.user_id,
        action="variant_stock_updated",
        entity_type="variant",
        entity_id=variant.id,
        detail=changes or None,
    )
    db.commit()


@router.patch("/admin/variants/{variant_id}", status_code=204)
def patch_variant(
    variant_id: str,
    data: AdminVariantUpdateIn,
    session: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    if data.price_sgd_cents is None and data.stock_on_hand is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")
    variant = db.get(Variant, _parse_uuid_or_404(variant_id, "Variant not found"))
    if not variant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
    changes = update_variant(
        db,
        variant,
        price_sgd_cents=data.price_sgd_cents,
        stock_on_hand=data.stock_on_hand,
        reason=data.reason,
    )
    write_audit(
        db,
        actor_user_id=session.user_id,
        action="variant_updated",
        entity_type="variant",
        entity_id=variant.id,
        detail=changes or None,
    )
    db.commit()


@router.post("/admin/products", response_model=ProductOut, status_code=201)
def create_admin_product(
    data: AdminProductIn,
    session: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    try:
        product = create_product(db, data)
        write_audit(
            db,
            actor_user_id=session.user_id,
            action="product_created",
            entity_type="product",
            entity_id=product.id,
            detail={"slug": product.slug, "name": product.name},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug or SKU already exists") from None
    db.refresh(product)
    return _product_out(product)


@router.patch("/admin/products/{product_id}", response_model=ProductOut)
def patch_admin_product(
    product_id: str,
    data: AdminProductUpdateIn,
    session: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    product = db.get(Product, _parse_uuid_or_404(product_id, "Product not found"))
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    changes = update_product(db, product, data)
    write_audit(
        db,
        actor_user_id=session.user_id,
        action="product_updated",
        entity_type="product",
        entity_id=product.id,
        detail=changes or None,
    )
    db.commit()
    db.refresh(product)
    return _product_out(product)


@router.get("/admin/orders", response_model=AdminOrderPage)
def admin_list_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    order_status = None
    if status_filter is not None:
        try:
            order_status = OrderStatus(status_filter)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid status") from None
    rows, total = list_orders_admin(db, order_status=order_status, page=page, page_size=page_size)
    return AdminOrderPage(
        items=[AdminOrderOut.model_validate(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.patch("/admin/orders/{order_id}", response_model=AdminOrderOut)
def admin_update_order(
    order_id: str,
    data: AdminOrderStatusIn,
    session: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    order = db.get(Order, _parse_uuid_or_404(order_id, "Order not found"))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    try:
        target = OrderStatus(data.status)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid status") from None
    previous = order.status
    apply_order_transition(db, order, target)
    write_audit(
        db,
        actor_user_id=session.user_id,
        action="order_status_changed",
        entity_type="order",
        entity_id=order.id,
        detail={"from": previous.value, "to": target.value, "note": data.note},
    )
    db.commit()
    db.refresh(order)
    return order


@router.get("/admin/audit-log", response_model=AuditLogPage)
def admin_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: LoginSession = Depends(admin_session),
    db: Session = Depends(get_db),
):
    rows, total = list_audit_log(db, page=page, page_size=page_size)
    return AuditLogPage(
        items=[
            AuditLogOut(
                id=row.id,
                actor_user_id=row.actor_user_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                detail=json.loads(row.detail) if row.detail else None,
                created_at=row.created_at,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
