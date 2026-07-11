import re
import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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
    caption: str | None = None
    media_type: Literal["image", "video"] = "image"


class AdminImageOut(ImageOut):
    id: uuid.UUID


class OptionChoiceOut(ApiModel):
    value: str
    label: str
    surcharge_cents: int = 0
    default: bool = False


class OptionGroupOut(ApiModel):
    key: str
    label: str
    choices: list[OptionChoiceOut]


class OptionChoiceIn(BaseModel):
    value: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    surcharge_cents: int = Field(default=0, ge=0, le=100000)
    default: bool = False


_OPTION_KEY_RE = re.compile(r"^[a-z0-9_]+$")


class OptionGroupIn(BaseModel):
    """One admin-editable customisation group (e.g. "Matcha") with its choices.

    Validated so a broken config can never be saved: at least one choice,
    exactly one default, unique choice values, and a slug-safe key (products'
    options_config is stored as opaque JSON, so nothing else checks this)."""

    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    choices: list[OptionChoiceIn] = Field(min_length=1)

    @field_validator("key")
    @classmethod
    def _slug_key(cls, value: str) -> str:
        if not _OPTION_KEY_RE.fullmatch(value):
            raise ValueError(
                "key must be lowercase letters, digits, and underscores only"
            )
        return value

    @model_validator(mode="after")
    def _validate_choices(self) -> "OptionGroupIn":
        values = [choice.value for choice in self.choices]
        if len(values) != len(set(values)):
            raise ValueError("choice values must be unique within a group")
        defaults = sum(1 for choice in self.choices if choice.default)
        if defaults != 1:
            raise ValueError("exactly one choice must be marked default")
        return self


def _validate_option_groups(
    groups: list[OptionGroupIn] | None,
) -> list[OptionGroupIn] | None:
    if groups is None:
        return None
    keys = [group.key for group in groups]
    if len(keys) != len(set(keys)):
        raise ValueError("option group keys must be unique")
    return groups


class ProductOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    category: str | None
    category_slug: str | None
    variants: list[VariantOut]
    images: list[ImageOut]
    options: list[OptionGroupOut] | None = None


class ProductPage(BaseModel):
    items: list[ProductOut]
    page: int
    page_size: int
    total: int


class AdminVariantOut(VariantOut):
    active: bool
    # The public VariantOut only exposes available_stock (on_hand - reserved);
    # admin needs the true on-hand figure to edit it without silently
    # shrinking stock out from under active reservations.
    stock_on_hand: int
    stock_reserved: int


class AdminCatalogProductOut(ApiModel):
    """Like ProductOut, but includes inactive products/variants and their
    active flag -- the public ProductOut/VariantOut deliberately hide both, so
    the admin catalog view needs its own shape to manage a deactivated
    listing back to active."""

    id: uuid.UUID
    slug: str
    name: str
    description: str
    active: bool
    category: str | None
    category_slug: str | None
    variants: list[AdminVariantOut]
    images: list[AdminImageOut]
    options: list[OptionGroupOut] | None = None


class AdminCatalogPage(BaseModel):
    items: list[AdminCatalogProductOut]
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


class DrinkOptionsIn(BaseModel):
    """Per-line customisation for a drink. Unknown keys are rejected (422) rather
    than silently ignored, so a typo in a future field doesn't get dropped
    without notice."""

    model_config = ConfigDict(extra="forbid")

    matcha_g: Literal[4, 6] = 4
    whisk: Literal["water", "oat"] = "water"
    base_milk: Literal["cow", "oat"] = "cow"
    milk_ml: Literal[130, 160] = 130
    sugar_g: Literal[2, 4, 6, 8] = 4


class CartItemIn(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=20)
    # Loosely typed on purpose: the set of valid keys/values is defined per
    # product by Product.options_config (admin-editable), not by a fixed
    # schema here -- see services.cart for the actual validation against it.
    options: dict[str, str | int] | None = None


class CartItemOut(BaseModel):
    id: uuid.UUID
    variant_id: uuid.UUID
    product_slug: str
    product_name: str
    variant_name: str
    sku: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    options: dict | None = None
    options_label: str | None = None


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
    # Optional because a logged-in checkout always uses the session user's
    # email (see create_pending_order); guests still need one, enforced
    # there rather than here so the error message can be friendlier than a
    # generic field-required 422.
    email: EmailStr | None = None
    shipping_address: AddressIn | None = None
    pickup_at: datetime | None = None
    coupon_code: str | None = Field(default=None, max_length=40)
    payment_method: Literal["online", "pay_at_pickup"] = "online"
    # A Telegram/WhatsApp handle to fall back on if the confirmation email
    # doesn't reach the customer. Purely for the shop's use -- never emailed.
    contact_handle: str | None = Field(default=None, max_length=120)

    @field_validator("contact_handle", mode="before")
    @classmethod
    def _blank_contact_handle_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class CheckoutOut(BaseModel):
    order_id: uuid.UUID
    display_number: str
    checkout_url: str
    guest_lookup_token: str | None
    reservation_expires_at: datetime | None = None


class OrderItemOut(ApiModel):
    product_name: str
    variant_name: str
    sku: str
    unit_price_cents: int
    quantity: int
    options: dict | None = None
    options_label: str | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _parse_options(cls, value: object) -> object:
        # OrderItem.options is stored as a serialised JSON string (see the model
        # docstring); decode it here so API consumers always see a plain dict.
        if isinstance(value, str):
            import json

            return json.loads(value)
        return value


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
    payment_method: str
    items: list[OrderItemOut]


class AdminStockIn(BaseModel):
    stock_on_hand: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=80)


class AdminOrderOut(OrderOut):
    created_at: datetime
    user_id: uuid.UUID | None
    contact_handle: str | None = None


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
    caption: str | None = Field(default=None, max_length=300)
    position: int = Field(default=0, ge=0)
    media_type: Literal["image", "video"] = "image"


class AdminImageUpdateIn(BaseModel):
    alt_text: str | None = Field(default=None, max_length=240)
    caption: str | None = Field(default=None, max_length=300)


class AdminImageOrderIn(BaseModel):
    image_ids: list[uuid.UUID] = Field(min_length=1)


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
    options: list[OptionGroupIn] | None = None

    @field_validator("options")
    @classmethod
    def _check_option_groups(
        cls, value: list[OptionGroupIn] | None
    ) -> list[OptionGroupIn] | None:
        return _validate_option_groups(value)


class AdminProductUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1)
    active: bool | None = None
    # None = leave options unchanged; an explicit [] clears all option groups.
    options: list[OptionGroupIn] | None = None

    @field_validator("options")
    @classmethod
    def _check_option_groups(
        cls, value: list[OptionGroupIn] | None
    ) -> list[OptionGroupIn] | None:
        return _validate_option_groups(value)


class AdminVariantUpdateIn(BaseModel):
    price_cents: int | None = Field(default=None, ge=0)
    stock_on_hand: int | None = Field(default=None, ge=0)
    active: bool | None = None
    reason: str = Field(min_length=3, max_length=80)


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_name: str
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


class NoticeOut(ApiModel):
    id: uuid.UUID
    title: str
    body: str
    created_at: datetime


class AdminNoticeOut(NoticeOut):
    active: bool
    updated_at: datetime


class AdminNoticeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)


class AdminNoticeUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    active: bool | None = None


class AdminPickupDayUpdateIn(BaseModel):
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = Field(default=None, gt=0, le=240)
    slot_capacity: int | None = Field(default=None, gt=0, le=100)
    is_available: bool | None = None


class StorefrontConfigOut(BaseModel):
    online_payments_enabled: bool
