import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VariantOut(ApiModel):
    id: uuid.UUID
    sku: str
    name: str
    weight_grams: int
    price_sgd_cents: int
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
    currency: str = "SGD"


class AddressIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=120)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=32)
    country_code: str = Field(min_length=2, max_length=2)


class CheckoutIn(BaseModel):
    email: EmailStr
    shipping_address: AddressIn
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
    items: list[OrderItemOut]


class AdminStockIn(BaseModel):
    stock_on_hand: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=80)
