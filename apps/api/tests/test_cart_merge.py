from test_checkout import add_product

from app.models import Category, Product, Variant


def add_second_product(db, stock=50):
    category = Category(name="Sencha", slug="sencha")
    product = Product(
        category=category,
        name="Second Matcha",
        slug="second-matcha",
        description="Another test product",
        variants=[
            Variant(
                sku="TEST-40",
                name="40 g",
                weight_grams=40,
                price_sgd_cents=4000,
                stock_on_hand=stock,
            )
        ],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def test_merge_combines_quantities_for_shared_variant(client, db):
    # services/cart.merge_guest_cart: when both the guest cart and the account cart
    # already contain the same variant, quantities are summed (capped by available
    # stock and a hard cap of 20), not replaced.
    product = add_product(db, stock=50)
    variant = product.variants[0]

    # Guest adds 2 units before registering.
    guest_add = client.put(
        "/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 2}
    )
    assert guest_add.status_code == 200

    register = client.post(
        "/api/v1/auth/register",
        json={"email": "shopper@example.com", "password": "long-password", "name": "Shopper"},
    )
    assert register.status_code == 201

    cart = client.get("/api/v1/cart").json()
    assert cart["subtotal_cents"] == 2 * 3200
    assert cart["items"][0]["quantity"] == 2


def test_merge_adds_distinct_variant_from_guest_cart_into_account_cart(client, db):
    first = add_product(db, stock=10)
    second = add_second_product(db, stock=10)

    # Log in first to create/attach an account cart with one item.
    register = client.post(
        "/api/v1/auth/register",
        json={"email": "shopper2@example.com", "password": "long-password", "name": "Shopper"},
    )
    account_add = client.put(
        "/api/v1/cart/items", json={"variant_id": str(first.variants[0].id), "quantity": 1}
    )
    assert account_add.status_code == 200

    # /auth/logout requires the CSRF token from the session; omitting it returns
    # 403 and silently leaves the session active, which would invalidate this test.
    csrf_token = register.json()["csrf_token"]
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 204

    # Now, as a guest (new cart cookie), add the second product then log back in.
    guest_add = client.put(
        "/api/v1/cart/items", json={"variant_id": str(second.variants[0].id), "quantity": 3}
    )
    assert guest_add.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "shopper2@example.com", "password": "long-password"},
    )
    assert login.status_code == 200

    cart = client.get("/api/v1/cart").json()
    quantities_by_variant = {item["variant_id"]: item["quantity"] for item in cart["items"]}

    # services/cart.py merge_guest_cart's "distinct variant" branch re-parents
    # the guest item onto the account cart (removing it from guest_cart.items
    # and appending it to account_cart.items) before the guest cart is
    # deleted, so both the pre-existing account item and the transferred
    # guest item survive the merge.
    assert str(first.variants[0].id) in quantities_by_variant
    assert quantities_by_variant[str(first.variants[0].id)] == 1
    assert str(second.variants[0].id) in quantities_by_variant
    assert quantities_by_variant[str(second.variants[0].id)] == 3


def test_merge_caps_combined_quantity_at_available_stock_and_hard_limit(client, db):
    # Guest cart has 15 units reserved in-cart; account cart already has 10 of the
    # same variant. 15 + 10 = 25, but available_stock is capped at 20 (stock_on_hand)
    # and merge additionally hard-caps at 20, so the merged quantity should be 20.
    product = add_product(db, stock=25)
    variant = product.variants[0]

    register = client.post(
        "/api/v1/auth/register",
        json={"email": "shopper3@example.com", "password": "long-password", "name": "Shopper"},
    )
    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 10})
    logout = client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": register.json()["csrf_token"]}
    )
    assert logout.status_code == 204

    client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 15})

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "shopper3@example.com", "password": "long-password"},
    )
    assert login.status_code == 200

    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["quantity"] == 20
