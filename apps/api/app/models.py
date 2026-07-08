import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .db import Base


class Role(str, enum.Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FULFILLED = "fulfilled"
    REFUNDED = "refunded"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CUSTOMER)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class Address(TimestampMixin, Base):
    __tablename__ = "addresses"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(120))
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))
    postal_code: Mapped[str] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(2))


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    category: Mapped[Category | None] = relationship()
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        cascade="all, delete-orphan", order_by="ProductImage.position", lazy="selectin"
    )


class ProductImage(Base):
    __tablename__ = "product_images"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1000))
    alt_text: Mapped[str] = mapped_column(String(240))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Variant(TimestampMixin, Base):
    __tablename__ = "variants"
    __table_args__ = (
        CheckConstraint("price_cents >= 0"),
        CheckConstraint("weight_grams > 0"),
        CheckConstraint("stock_on_hand >= 0"),
        CheckConstraint("stock_reserved >= 0 AND stock_reserved <= stock_on_hand"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    weight_grams: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int] = mapped_column(Integer)
    stock_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    stock_reserved: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped[Product] = relationship(back_populates="variants")

    @property
    def available_stock(self) -> int:
        return self.stock_on_hand - self.stock_reserved


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("variants.id"), index=True)
    quantity_delta: Mapped[int] = mapped_column(Integer)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Cart(TimestampMixin, Base):
    __tablename__ = "carts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["CartItem"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id"), CheckConstraint("quantity > 0"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"))
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("variants.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    variant: Mapped[Variant] = relationship(lazy="joined")


class Coupon(TimestampMixin, Base):
    __tablename__ = "coupons"
    __table_args__ = (CheckConstraint("percent_off BETWEEN 1 AND 100"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    percent_off: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    display_number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    lookup_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), index=True)
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="SEK")
    shipping_name: Mapped[str] = mapped_column(String(120))
    shipping_line1: Mapped[str] = mapped_column(String(200))
    shipping_line2: Mapped[str | None] = mapped_column(String(200))
    shipping_city: Mapped[str] = mapped_column(String(120))
    shipping_postal_code: Mapped[str] = mapped_column(String(32))
    shipping_country_code: Mapped[str] = mapped_column(String(2))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    payment: Mapped["Payment | None"] = relationship(
        back_populates="order", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("unit_price_cents >= 0"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("variants.id"))
    product_name: Mapped[str] = mapped_column(String(160))
    variant_name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(80))
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), default="stripe")
    provider_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="SEK")
    order: Mapped[Order] = relationship(back_populates="payment")


class ProcessedWebhook(Base):
    __tablename__ = "processed_webhooks"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    carrier: Mapped[str] = mapped_column(String(80))
    tracking_number: Mapped[str] = mapped_column(String(160))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        CheckConstraint("rating BETWEEN 1 AND 5"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id"))
    rating: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AdminAuditLog(Base):
    """One row per admin mutation, written in the same transaction as the change.

    `detail` holds a small JSON-serialised dict of context (e.g. old/new status,
    changed fields) rather than a typed column set, since the shape varies by
    action; callers should treat it as write-once diagnostic/compliance data,
    not a queryable structure.
    """

    __tablename__ = "admin_audit_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


Index("ix_orders_expirable", Order.status, Order.reservation_expires_at)
Index("ix_rate_limit_events_key_created_at", RateLimitEvent.key, RateLimitEvent.created_at)
