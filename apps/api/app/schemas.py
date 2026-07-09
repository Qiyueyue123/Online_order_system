import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VariantOut(ApiModel):
    id: uuid.UUID
    sku: str
    name: str
    weight_grams: int
    price_cents: int
    available_stock: int


class ImageOut(ApiModel):
    url: str
    alt_text: str


class ProductOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    category: str | None
    variants: list[VariantOut]
    images: list[ImageOut]


class ProductPage(BaseModel):
    items: list[ProductOut]
    page: int
    page_size: int
    total: int


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ApiModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    email_verified: bool


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class CartItemIn(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=20)


class CartItemOut(BaseModel):
    variant_id: uuid.UUID
    product_slug: str
    product_name: str
    variant_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class CartOut(BaseModel):
    items: list[CartItemOut]
    subtotal_cents: int
    currency: str = "SEK"
    needs_pickup: bool = False
    needs_shipping: bool = False


class AddressIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=120)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=32)
    country_code: str = Field(min_length=2, max_length=2)


class CheckoutIn(BaseModel):
    email: EmailStr
    shipping_address: AddressIn | None = None
    pickup_at: datetime | None = None
    coupon_code: str | None = Field(default=None, max_length=40)


class CheckoutOut(BaseModel):
    order_id: uuid.UUID
    display_number: str
    checkout_url: str
    guest_lookup_token: str | None
    reservation_expires_at: datetime


class OrderItemOut(ApiModel):
    product_name: str
    variant_name: str
    sku: str
    unit_price_cents: int
    quantity: int


class OrderOut(ApiModel):
    id: uuid.UUID
    display_number: str
    status: str
    email: EmailStr
    subtotal_cents: int
    discount_cents: int
    shipping_cents: int
    total_cents: int
    currency: str
    pickup_at: datetime | None
    items: list[OrderItemOut]


class AdminStockIn(BaseModel):
    stock_on_hand: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=80)


class AdminOrderOut(OrderOut):
    created_at: datetime
    user_id: uuid.UUID | None


class AdminOrderPage(BaseModel):
    items: list[AdminOrderOut]
    page: int
    page_size: int
    total: int


class AdminOrderStatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=240)


class AdminImageIn(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    alt_text: str = Field(default="", max_length=240)
    position: int = Field(default=0, ge=0)


class AdminVariantCreateIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    weight_grams: int = Field(gt=0)
    price_cents: int = Field(ge=0)
    stock_on_hand: int = Field(default=0, ge=0)


class AdminProductIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    category_slug: str | None = Field(default=None, max_length=80)
    images: list[AdminImageIn] = Field(default_factory=list)
    variants: list[AdminVariantCreateIn] = Field(min_length=1)


class AdminProductUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1)
    active: bool | None = None


class AdminVariantUpdateIn(BaseModel):
    price_cents: int | None = Field(default=None, ge=0)
    stock_on_hand: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=3, max_length=80)


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str
    detail: dict | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    page: int
    page_size: int
    total: int


class PickupSlotOut(BaseModel):
    time: datetime
    remaining: int


class PickupDayPublicOut(BaseModel):
    date: date
    slots: list[PickupSlotOut]


class AdminPickupDayOut(ApiModel):
    id: uuid.UUID
    date: date
    start_time: time
    end_time: time
    slot_minutes: int
    slot_capacity: int
    is_available: bool


class AdminPickupDayIn(BaseModel):
    date: date
    start_time: time
    end_time: time
    slot_minutes: int = Field(default=15, gt=0, le=240)
    slot_capacity: int = Field(default=2, gt=0, le=100)


class AdminPickupDayUpdateIn(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = Field(default=None, gt=0, le=240)
    slot_capacity: int | None = Field(default=None, gt=0, le=100)
    is_available: bool | None = None
