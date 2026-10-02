import itertools
import os
from datetime import UTC, datetime

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RESERVATION_SWEEP_INTERVAL_SECONDS"] = "0"
# Online payments default off in production; most existing checkout tests
# exercise the "online" payment_method path, so keep it on by default here
# and let the specific disabled-flow tests override settings themselves.
os.environ["ONLINE_PAYMENTS_ENABLED"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    Category,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    Variant,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


_product_counter = itertools.count()


def add_product(db, stock=3, *, unique=False):
    """Insert a category + single-variant product for tests. `unique=True` appends
    a process-wide counter to the slug/sku/category slug, for tests that call this
    (directly or via make_order/pending_order) more than once against the same db
    session and would otherwise collide on the fixed "test-matcha" slug."""
    suffix = f"-{next(_product_counter)}" if unique else ""
    category = Category(name="Matcha", slug=f"matcha{suffix}")
    product = Product(
        category=category,
        name="Test Matcha",
        slug=f"test-matcha{suffix}",
        description="A test product",
        variants=[
            Variant(
                sku=f"TEST-30{suffix}",
                name="30 g",
                weight_grams=30,
                price_cents=3200,
                stock_on_hand=stock,
            )
        ],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def pending_order(db, *, stock=4, reserved=2, quantity=2):
    """A PENDING_PAYMENT order over one add_product() variant, with the given
    stock/reserved/quantity already applied. Shared by test_webhook and
    test_inventory_states."""
    product = add_product(db, stock=stock)
    variant = product.variants[0]
    variant.stock_reserved = reserved
    order = Order(
        display_number="M-STATE-1",
        email="guest@example.com",
        status=OrderStatus.PENDING_PAYMENT,
        subtotal_cents=3200 * quantity,
        shipping_cents=600,
        total_cents=3200 * quantity + 600,
        shipping_name="Guest",
        shipping_line1="1 Tea Street",
        shipping_city="Umea",
        shipping_postal_code="90325",
        shipping_country_code="SE",
        reservation_expires_at=datetime.now(UTC),
        items=[
            OrderItem(
                variant_id=variant.id,
                product_name=product.name,
                variant_name=variant.name,
                sku=variant.sku,
                unit_price_cents=3200,
                quantity=quantity,
            )
        ],
        payment=Payment(status=PaymentStatus.PENDING, amount_cents=3200 * quantity + 600),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order, variant


def make_order(db, order_status, *, stock=4, reserved=2):
    """A order in `order_status`, over one (uniquely-slugged) add_product() variant,
    with `reserved` units already marked reserved. Shared by test_admin's order
    listing/transition tests, several of which create more than one order per test."""
    product = add_product(db, stock=stock, unique=True)
    variant = product.variants[0]
    variant.stock_reserved = reserved
    order = Order(
        display_number=f"M-ADMIN-{order_status.value}",
        email="guest@example.com",
        status=order_status,
        subtotal_cents=6400,
        shipping_cents=600,
        total_cents=7000,
        shipping_name="Guest",
        shipping_line1="1 Tea Street",
        shipping_city="Umea",
        shipping_postal_code="90325",
        shipping_country_code="SE",
        reservation_expires_at=(
            datetime.now(UTC) if order_status == OrderStatus.PENDING_PAYMENT else None
        ),
        items=[
            OrderItem(
                variant_id=variant.id,
                product_name=product.name,
                variant_name=variant.name,
                sku=variant.sku,
                unit_price_cents=3200,
                quantity=2,
            )
        ],
        payment=Payment(
            status=PaymentStatus.SUCCEEDED
            if order_status == OrderStatus.PAID
            else PaymentStatus.PENDING,
            amount_cents=7000,
        ),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order, variant


ADDRESS = {
    "recipient_name": "Guest",
    "line1": "1 Tea Street",
    "city": "Umea",
    "postal_code": "90325",
    "country_code": "SE",
}


def checkout(
    client, *, pickup_at=None, address=None, email="guest@example.com", payment_method=None
):
    body = {"email": email}
    if pickup_at is not None:
        body["pickup_at"] = pickup_at
    if address is not None:
        body["shipping_address"] = address
    if payment_method is not None:
        body["payment_method"] = payment_method
    return client.post("/api/v1/checkout", json=body)


def put_item(client, variant, quantity=1, options=None):
    body = {"variant_id": str(variant.id), "quantity": quantity}
    if options is not None:
        body["options"] = options
    response = client.put("/api/v1/cart/items", json=body)
    assert response.status_code == 200
    return response
