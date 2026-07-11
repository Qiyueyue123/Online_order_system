from conftest import add_product, make_order

from app.models import AdminAuditLog, OrderStatus, Role, User
from app.security import hash_password

ADMIN_PASSWORD = "admin-password-123"


def make_admin(db, email="admin@example.com"):
    user = User(
        email=email,
        name="Admin",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=Role.ADMIN,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def admin_headers(client, db, email="admin@example.com"):
    make_admin(db, email)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def customer_headers(client, email="shopper@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "long-password", "name": "Shopper"},
    )
    assert response.status_code == 201
    return {"X-CSRF-Token": response.json()["csrf_token"]}


PRODUCT_BODY = {
    "slug": "new-blend",
    "name": "New Blend",
    "description": "A fresh matcha blend",
    "variants": [
        {
            "sku": "NEW-30",
            "name": "30 g tin",
            "weight_grams": 30,
            "price_cents": 4200,
            "stock_on_hand": 10,
        }
    ],
}

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/orders", None),
    (
        "PATCH",
        "/api/v1/admin/orders/00000000-0000-0000-0000-000000000000",
        {"status": "fulfilled"},
    ),
    ("POST", "/api/v1/admin/products", PRODUCT_BODY),
    (
        "PATCH",
        "/api/v1/admin/products/00000000-0000-0000-0000-000000000000",
        {"active": False},
    ),
    (
        "PATCH",
        "/api/v1/admin/variants/00000000-0000-0000-0000-000000000000",
        {"price_cents": 100, "reason": "test adjustment"},
    ),
    (
        "PATCH",
        "/api/v1/admin/variants/00000000-0000-0000-0000-000000000000/stock",
        {"stock_on_hand": 1, "reason": "test adjustment"},
    ),
    ("GET", "/api/v1/admin/audit-log", None),
    ("GET", "/api/v1/admin/products", None),
    (
        "POST",
        "/api/v1/admin/products/00000000-0000-0000-0000-000000000000/images",
        {"url": "https://example.com/photo.jpg"},
    ),
    (
        "PATCH",
        "/api/v1/admin/products/00000000-0000-0000-0000-000000000000/images/"
        "00000000-0000-0000-0000-000000000000",
        {"caption": "Nope"},
    ),
    (
        "DELETE",
        "/api/v1/admin/products/00000000-0000-0000-0000-000000000000/images/"
        "00000000-0000-0000-0000-000000000000",
        None,
    ),
]


def test_admin_routes_require_authentication(client):
    for method, path, body in ADMIN_ROUTES:
        response = client.request(method, path, json=body)
        assert response.status_code == 401, path


def test_admin_routes_reject_customer_role(client):
    headers = customer_headers(client)
    for method, path, body in ADMIN_ROUTES:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, path


def test_admin_can_create_product(client, db):
    headers = admin_headers(client, db)
    response = client.post("/api/v1/admin/products", json=PRODUCT_BODY, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "new-blend"
    assert body["variants"][0]["sku"] == "NEW-30"

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="product_created").one()
    assert log.actor_user_id == admin.id
    assert log.entity_type == "product"


def test_admin_create_product_rejects_duplicate_slug(client, db):
    headers = admin_headers(client, db)
    first = client.post("/api/v1/admin/products", json=PRODUCT_BODY, headers=headers)
    assert first.status_code == 201
    second = client.post("/api/v1/admin/products", json=PRODUCT_BODY, headers=headers)
    assert second.status_code == 409


def test_admin_products_list_includes_deactivated_listings(client, db):
    """The public /products endpoint hides inactive products/variants (by
    design), so admin needs its own listing or a deactivated product becomes
    permanently invisible -- including to the admin who deactivated it."""
    headers = admin_headers(client, db)
    product = add_product(db)
    variant = product.variants[0]

    active_only = client.get("/api/v1/admin/products", headers=headers).json()
    assert any(item["slug"] == product.slug for item in active_only["items"])

    client.patch(
        f"/api/v1/admin/products/{product.id}",
        json={"active": False},
        headers=headers,
    )
    client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"active": False, "reason": "discontinued"},
        headers=headers,
    )

    public_list = client.get("/api/v1/products").json()
    assert not any(item["slug"] == product.slug for item in public_list["items"])

    admin_list = client.get("/api/v1/admin/products", headers=headers).json()
    entry = next(item for item in admin_list["items"] if item["slug"] == product.slug)
    assert entry["active"] is False
    assert entry["variants"][0]["active"] is False


def test_admin_products_list_requires_admin_role(client):
    response = client.get("/api/v1/admin/products")
    assert response.status_code == 401


def test_admin_can_update_product(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    response = client.patch(
        f"/api/v1/admin/products/{product.id}",
        json={"name": "Renamed Matcha", "active": False},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Matcha"

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="product_updated").one()
    assert log.actor_user_id == admin.id
    assert log.entity_id == str(product.id)


def test_admin_can_update_variant_price_and_stock(client, db):
    headers = admin_headers(client, db)
    product = add_product(db, stock=5)
    variant = product.variants[0]
    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"price_cents": 5000, "stock_on_hand": 20, "reason": "restock and reprice"},
        headers=headers,
    )
    assert response.status_code == 204
    db.refresh(variant)
    assert variant.price_cents == 5000
    assert variant.stock_on_hand == 20

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="variant_updated").one()
    assert log.actor_user_id == admin.id


def test_admin_can_deactivate_and_reactivate_a_variant(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    variant = product.variants[0]
    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"active": False, "reason": "discontinuing this listing"},
        headers=headers,
    )
    assert response.status_code == 204
    db.refresh(variant)
    assert variant.active is False

    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"active": True, "reason": "back in stock"},
        headers=headers,
    )
    assert response.status_code == 204
    db.refresh(variant)
    assert variant.active is True


def test_admin_can_add_and_remove_a_product_image(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)

    added = client.post(
        f"/api/v1/admin/products/{product.id}/images",
        json={"url": "https://example.com/photo.jpg", "alt_text": "A jar of matcha", "position": 0},
        headers=headers,
    )
    assert added.status_code == 201
    body = added.json()
    assert len(body["images"]) == 1
    image = body["images"][0]
    assert image["url"] == "https://example.com/photo.jpg"
    assert image["media_type"] == "image"

    log = db.query(AdminAuditLog).filter_by(action="product_image_added").one()
    assert log.entity_id == str(product.id)

    removed = client.delete(
        f"/api/v1/admin/products/{product.id}/images/{image['id']}",
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["images"] == []

    db.query(AdminAuditLog).filter_by(action="product_image_removed").one()


def test_admin_can_update_an_image_caption(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)

    added = client.post(
        f"/api/v1/admin/products/{product.id}/images",
        json={"url": "https://example.com/photo.jpg", "alt_text": "A jar of matcha", "position": 0},
        headers=headers,
    )
    image_id = added.json()["images"][0]["id"]

    patched = client.patch(
        f"/api/v1/admin/products/{product.id}/images/{image_id}",
        json={"caption": "Whisked to order"},
        headers=headers,
    )
    assert patched.status_code == 200
    image = patched.json()["images"][0]
    assert image["caption"] == "Whisked to order"
    assert image["alt_text"] == "A jar of matcha"

    log = db.query(AdminAuditLog).filter_by(action="product_image_updated").one()
    assert log.entity_id == str(product.id)

    no_csrf = client.patch(
        f"/api/v1/admin/products/{product.id}/images/{image_id}",
        json={"caption": "Nope"},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["detail"] == "Invalid CSRF token"


def test_admin_update_unknown_image_is_404(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    response = client.patch(
        f"/api/v1/admin/products/{product.id}/images/00000000-0000-0000-0000-000000000000",
        json={"caption": "Nope"},
        headers=headers,
    )
    assert response.status_code == 404


def test_admin_can_add_a_video(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)

    response = client.post(
        f"/api/v1/admin/products/{product.id}/images",
        json={
            "url": "https://example.com/clip.mp4",
            "alt_text": "Pouring the drink",
            "media_type": "video",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["images"][0]["media_type"] == "video"


def test_admin_remove_unknown_image_is_404(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    response = client.delete(
        f"/api/v1/admin/products/{product.id}/images/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == 404


def test_admin_variant_update_rejects_stock_below_reservations(client, db):
    headers = admin_headers(client, db)
    product = add_product(db, stock=5)
    variant = product.variants[0]
    variant.stock_reserved = 3
    db.commit()
    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"stock_on_hand": 1, "reason": "too low"},
        headers=headers,
    )
    assert response.status_code == 409


def test_admin_variant_update_requires_a_field(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    variant = product.variants[0]
    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}",
        json={"reason": "nothing changed"},
        headers=headers,
    )
    assert response.status_code == 400


def test_legacy_stock_endpoint_still_works_and_is_audited(client, db):
    headers = admin_headers(client, db)
    product = add_product(db, stock=5)
    variant = product.variants[0]
    response = client.patch(
        f"/api/v1/admin/variants/{variant.id}/stock",
        json={"stock_on_hand": 9, "reason": "stock count"},
        headers=headers,
    )
    assert response.status_code == 204
    db.refresh(variant)
    assert variant.stock_on_hand == 9

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="variant_stock_updated").one()
    assert log.actor_user_id == admin.id


def test_admin_orders_list_is_paginated_and_filterable(client, db):
    headers = admin_headers(client, db)
    make_order(db, OrderStatus.PENDING_PAYMENT)
    make_order(db, OrderStatus.PAID)

    all_orders = client.get("/api/v1/admin/orders", headers=headers)
    assert all_orders.status_code == 200
    assert all_orders.json()["total"] == 2

    paid_only = client.get("/api/v1/admin/orders?status=paid", headers=headers)
    assert paid_only.status_code == 200
    body = paid_only.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "paid"
    assert body["items"][0]["email"] == "guest@example.com"


def test_admin_orders_invalid_status_filter_is_rejected(client, db):
    headers = admin_headers(client, db)
    response = client.get("/api/v1/admin/orders?status=not-a-status", headers=headers)
    assert response.status_code == 422


def test_admin_get_routes_work_without_csrf_header(client, db):
    admin_headers(client, db)
    orders = client.get("/api/v1/admin/orders")
    assert orders.status_code == 200
    audit_log = client.get("/api/v1/admin/audit-log")
    assert audit_log.status_code == 200


def test_admin_mutation_without_csrf_header_is_rejected(client, db):
    admin_headers(client, db)
    order, _ = make_order(db, OrderStatus.PAID)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "fulfilled"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


def test_admin_get_routes_reject_customer_without_csrf_header(client):
    customer_headers(client)
    orders = client.get("/api/v1/admin/orders")
    assert orders.status_code == 403


def test_admin_can_fulfill_paid_order(client, db):
    headers = admin_headers(client, db)
    order, _ = make_order(db, OrderStatus.PAID)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "fulfilled"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"

    admin = db.query(User).filter_by(email="admin@example.com").one()
    log = db.query(AdminAuditLog).filter_by(action="order_status_changed").one()
    assert log.actor_user_id == admin.id
    assert log.entity_id == str(order.id)


def test_admin_can_cancel_pending_order_and_release_stock(client, db):
    headers = admin_headers(client, db)
    order, variant = make_order(db, OrderStatus.PENDING_PAYMENT, stock=4, reserved=2)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "cancelled", "note": "customer asked to cancel"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db.refresh(variant)
    assert variant.stock_reserved == 0
    assert variant.stock_on_hand == 4


def test_admin_can_refund_paid_order(client, db):
    headers = admin_headers(client, db)
    order, _ = make_order(db, OrderStatus.PAID)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "refunded"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "refunded"


def test_admin_order_transition_rejects_invalid_move(client, db):
    headers = admin_headers(client, db)
    order, _ = make_order(db, OrderStatus.PENDING_PAYMENT)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "fulfilled"},
        headers=headers,
    )
    assert response.status_code == 409


def test_admin_order_transition_rejects_already_terminal_order(client, db):
    headers = admin_headers(client, db)
    order, _ = make_order(db, OrderStatus.CANCELLED)
    response = client.patch(
        f"/api/v1/admin/orders/{order.id}",
        json={"status": "fulfilled"},
        headers=headers,
    )
    assert response.status_code == 409


def test_audit_log_is_paginated_newest_first(client, db):
    headers = admin_headers(client, db)
    product = add_product(db)
    client.patch(
        f"/api/v1/admin/products/{product.id}",
        json={"name": "First rename"},
        headers=headers,
    )
    client.patch(
        f"/api/v1/admin/products/{product.id}",
        json={"name": "Second rename"},
        headers=headers,
    )
    response = client.get("/api/v1/admin/audit-log", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["detail"]["name"]["to"] == "Second rename"
    assert body["items"][1]["detail"]["name"]["to"] == "First rename"
    assert body["items"][0]["actor_name"] == "Admin"
