import itertools
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from conftest import ADDRESS, checkout, put_item

from app.models import AdminAuditLog, Category, Order, OrderStatus, PickupDay, Product, Variant
from app.services.email import _render_order_confirmation
from tests.test_admin import admin_headers, customer_headers

# Pickup times are wall-clock times at the café; slot instants sent to and from
# the API are the UTC equivalents (16:00 Stockholm = 14:00Z in summer).
CAFE_TZ = ZoneInfo("Europe/Stockholm")

_counter = itertools.count()


def add_drink(db, stock=30):
    n = next(_counter)
    category = db.query(Category).filter_by(slug="drinks").one_or_none()
    if category is None:
        category = Category(name="Drinks", slug="drinks")
    product = Product(
        category=category,
        name="Test Latte",
        slug=f"test-latte-{n}",
        description="A test drink",
        variants=[
            Variant(
                sku=f"LATTE-{n}",
                name="Iced",
                weight_grams=350,
                price_cents=4900,
                stock_on_hand=stock,
            )
        ],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def add_retail(db, stock=10):
    n = next(_counter)
    category = db.query(Category).filter_by(slug="matcha").one_or_none()
    if category is None:
        category = Category(name="Matcha tins", slug="matcha")
    product = Product(
        category=category,
        name="Test Tin",
        slug=f"test-tin-{n}",
        description="A test tin",
        variants=[
            Variant(
                sku=f"TIN-{n}",
                name="30 g",
                weight_grams=30,
                price_cents=24900,
                stock_on_hand=stock,
            )
        ],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def add_pickup_day(db, days_ahead=1, capacity=2, available=True):
    day = PickupDay(
        date=(datetime.now(UTC) + timedelta(days=days_ahead)).date(),
        start_time=time(16, 0),
        end_time=time(19, 0),
        slot_minutes=15,
        slot_capacity=capacity,
        is_available=available,
    )
    db.add(day)
    db.commit()
    db.refresh(day)
    return day


def slot_dt(day, hour=16, minute=0):
    """Aware datetime for `hour:minute` café time on the given PickupDay."""
    return datetime.combine(day.date, time(hour, minute), tzinfo=CAFE_TZ)


def slot_iso(day, hour=16, minute=0):
    return slot_dt(day, hour, minute).isoformat()


def utc_prefix(day, hour, minute):
    """The 'YYYY-MM-DDTHH:MM' UTC prefix the API serialises this café slot as."""
    return slot_dt(day, hour, minute).astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


# --- cart classification -------------------------------------------------


def test_cart_reports_needs_pickup_and_needs_shipping(client, db):
    drink = add_drink(db)
    retail = add_retail(db)

    response = put_item(client, drink.variants[0])
    assert response.json()["needs_pickup"] is True
    assert response.json()["needs_shipping"] is False

    response = put_item(client, retail.variants[0])
    assert response.json()["needs_pickup"] is True
    assert response.json()["needs_shipping"] is True


# --- public pickup-days --------------------------------------------------


def test_public_pickup_days_shape_and_future_only(client, db):
    day = add_pickup_day(db, days_ahead=1)
    add_pickup_day(db, days_ahead=2, available=False)  # hidden from public list

    response = client.get("/api/v1/pickup-days")
    assert response.status_code == 200
    body = response.json()
    assert [entry["date"] for entry in body] == [day.date.isoformat()]
    slots = body[0]["slots"]
    # 16:00-19:00 in 15-minute steps = 12 slots, all in the future with capacity 2
    assert len(slots) == 12
    assert all(slot["remaining"] == 2 for slot in slots)
    assert slots[0]["time"].startswith(utc_prefix(day, 16, 0))

    # A past day never shows up even when marked available.
    past = PickupDay(
        date=(datetime.now(UTC) - timedelta(days=1)).date(),
        start_time=time(16, 0),
        end_time=time(19, 0),
    )
    db.add(past)
    db.commit()
    response = client.get("/api/v1/pickup-days")
    assert [entry["date"] for entry in response.json()] == [day.date.isoformat()]


def test_slots_are_cafe_wall_clock_times_serialised_as_utc(client, db):
    # A 16:00-19:00 day means café wall-clock time (Europe/Stockholm). In July
    # (CEST, UTC+2) the first slot must therefore be 14:00Z — not 16:00Z.
    summer = date(2027, 7, 15)  # fixed future date so the DST offset is stable
    db.add(PickupDay(date=summer, start_time=time(16, 0), end_time=time(19, 0)))
    db.commit()

    body = client.get("/api/v1/pickup-days").json()
    entry = next(e for e in body if e["date"] == "2027-07-15")
    assert entry["slots"][0]["time"] in (
        "2027-07-15T14:00:00Z",
        "2027-07-15T14:00:00+00:00",
    )


# --- checkout adaptivity -------------------------------------------------


def test_drink_cart_requires_pickup_at(client, db):
    drink = add_drink(db)
    add_pickup_day(db)
    put_item(client, drink.variants[0])

    response = checkout(client)  # neither pickup nor address
    assert response.status_code == 422

    # Address alone does not satisfy a drinks cart.
    response = checkout(client, address=ADDRESS)
    assert response.status_code == 422


def test_retail_cart_requires_address_not_pickup(client, db):
    retail = add_retail(db)
    day = add_pickup_day(db)
    put_item(client, retail.variants[0])

    response = checkout(client, pickup_at=slot_iso(day))
    assert response.status_code == 422

    response = checkout(client, address=ADDRESS)
    assert response.status_code == 201
    order = db.query(Order).one()
    assert order.pickup_at is None
    assert order.shipping_cents == 0  # SE stays free


def test_pickup_only_order_persists_slot_and_skips_shipping(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])

    response = checkout(client, pickup_at=slot_iso(day, 16, 15))
    assert response.status_code == 201
    order = db.query(Order).one()
    assert order.pickup_at is not None
    assert order.shipping_cents == 0
    assert order.shipping_name is None
    assert order.shipping_country_code is None


def test_mixed_cart_requires_both(client, db):
    drink = add_drink(db)
    retail = add_retail(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    put_item(client, retail.variants[0])

    assert checkout(client, pickup_at=slot_iso(day)).status_code == 422
    assert checkout(client, address=ADDRESS).status_code == 422
    response = checkout(client, pickup_at=slot_iso(day), address=ADDRESS)
    assert response.status_code == 201
    order = db.query(Order).one()
    assert order.pickup_at is not None
    assert order.shipping_line1 == "1 Tea Street"


def test_off_grid_or_unavailable_slots_rejected(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    closed = add_pickup_day(db, days_ahead=3, available=False)
    put_item(client, drink.variants[0])

    # Not on the 15-minute grid.
    assert checkout(client, pickup_at=slot_iso(day, 16, 7)).status_code == 422
    # Outside the day's window.
    assert checkout(client, pickup_at=slot_iso(day, 19, 0)).status_code == 422
    # Day exists but is switched off.
    assert checkout(client, pickup_at=slot_iso(closed)).status_code == 422
    # No PickupDay row at all.
    no_day = (datetime.now(UTC) + timedelta(days=5)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    assert checkout(client, pickup_at=no_day.isoformat()).status_code == 422


# --- capacity ------------------------------------------------------------


def test_slot_capacity_enforced_and_freed_by_cancellation(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db, capacity=2)
    slot = slot_iso(day, 17, 0)

    for n in range(2):
        put_item(client, drink.variants[0])
        assert checkout(client, pickup_at=slot, email=f"guest{n}@example.com").status_code == 201

    # Capacity 2: the third order in the same slot is rejected under the day lock.
    put_item(client, drink.variants[0])
    assert checkout(client, pickup_at=slot).status_code == 409
    # A different slot on the same day still works.
    assert checkout(client, pickup_at=slot_iso(day, 17, 15)).status_code == 201

    # Cancelling one of the filled-slot orders frees a seat.
    cancelled = db.query(Order).filter_by(email="guest0@example.com").one()
    cancelled.status = OrderStatus.CANCELLED
    db.commit()
    put_item(client, drink.variants[0])
    assert checkout(client, pickup_at=slot).status_code == 201

    # The public list drops the once-again-full 17:00 slot but keeps its neighbours.
    times = [
        entry["time"]
        for day_entry in client.get("/api/v1/pickup-days").json()
        for entry in day_entry["slots"]
    ]
    assert not any(value.startswith(utc_prefix(day, 17, 0)) for value in times)
    assert any(value.startswith(utc_prefix(day, 17, 15)) for value in times)


# --- email ---------------------------------------------------------------


def test_receipt_shows_pickup_line_instead_of_shipping(client, db):
    drink = add_drink(db)
    day = add_pickup_day(db)
    put_item(client, drink.variants[0])
    assert checkout(client, pickup_at=slot_iso(day)).status_code == 201

    order = db.query(Order).one()
    body = _render_order_confirmation(order)
    assert "at the dorm kitchen, Umeå" in body
    # The receipt shows café wall-clock time (16:00), not the stored UTC instant.
    assert "16:00" in body
    assert "14:00" not in body
    assert "Shipping to:" not in body


def test_receipt_keeps_shipping_block_for_shipped_orders(client, db):
    retail = add_retail(db)
    put_item(client, retail.variants[0])
    assert checkout(client, address=ADDRESS).status_code == 201

    order = db.query(Order).one()
    body = _render_order_confirmation(order)
    assert "Shipping to:" in body
    assert "dorm kitchen" not in body


# --- admin CRUD ----------------------------------------------------------


def test_admin_pickup_day_crud_and_audit(client, db):
    headers = admin_headers(client, db)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()

    response = client.post(
        "/api/v1/admin/pickup-days",
        json={"date": tomorrow.isoformat(), "start_time": "16:00", "end_time": "19:00"},
        headers=headers,
    )
    assert response.status_code == 201
    created = response.json()
    assert created["slot_minutes"] == 15
    assert created["slot_capacity"] == 2
    assert created["is_available"] is True

    # Duplicate date is a conflict.
    response = client.post(
        "/api/v1/admin/pickup-days",
        json={"date": tomorrow.isoformat(), "start_time": "10:00", "end_time": "12:00"},
        headers=headers,
    )
    assert response.status_code == 409

    # Inverted window is rejected.
    response = client.post(
        "/api/v1/admin/pickup-days",
        json={
            "date": (tomorrow + timedelta(days=1)).isoformat(),
            "start_time": "19:00",
            "end_time": "16:00",
        },
        headers=headers,
    )
    assert response.status_code == 422

    response = client.patch(
        f"/api/v1/admin/pickup-days/{created['id']}",
        json={"is_available": False, "slot_capacity": 5},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["is_available"] is False
    assert response.json()["slot_capacity"] == 5

    # Admin list still shows the now-unavailable day; public list does not.
    admin_list = client.get("/api/v1/admin/pickup-days", headers=headers)
    assert [entry["id"] for entry in admin_list.json()] == [created["id"]]
    assert client.get("/api/v1/pickup-days").json() == []

    actions = [row.action for row in db.query(AdminAuditLog).order_by(AdminAuditLog.created_at)]
    assert actions == ["pickup_day_created", "pickup_day_updated"]
    updated = db.query(AdminAuditLog).filter_by(action="pickup_day_updated").one()
    assert "slot_capacity" in updated.detail


def test_admin_pickup_day_routes_require_admin(client, db):
    add_pickup_day(db)
    routes = [
        ("GET", "/api/v1/admin/pickup-days", None),
        (
            "POST",
            "/api/v1/admin/pickup-days",
            {"date": "2030-01-01", "start_time": "16:00", "end_time": "19:00"},
        ),
        (
            "PATCH",
            "/api/v1/admin/pickup-days/00000000-0000-0000-0000-000000000000",
            {"is_available": False},
        ),
    ]
    for method, path, body in routes:
        assert client.request(method, path, json=body).status_code == 401, path
    headers = customer_headers(client)
    for method, path, body in routes:
        assert client.request(method, path, json=body, headers=headers).status_code == 403, path
