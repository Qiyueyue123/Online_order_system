from app.models import Category, Product, Variant


def add_product(db, stock=3):
    category = Category(name="Matcha", slug="matcha")
    product = Product(
        category=category,
        name="Test Matcha",
        slug="test-matcha",
        description="A test product",
        variants=[
            Variant(
                sku="TEST-30",
                name="30 g",
                weight_grams=30,
                price_sgd_cents=3200,
                stock_on_hand=stock,
            )
        ],
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def test_checkout_reprices_on_server_and_reserves_stock(client, db):
    product = add_product(db)
    variant = product.variants[0]
    add = client.put("/api/v1/cart/items", json={"variant_id": str(variant.id), "quantity": 2})
    assert add.status_code == 200
    assert add.json()["subtotal_cents"] == 6400

    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Singapore",
                "postal_code": "018956",
                "country_code": "SG",
            },
        },
    )
    assert response.status_code == 201
    assert response.json()["guest_lookup_token"]
    db.refresh(variant)
    assert variant.stock_on_hand == 3
    assert variant.stock_reserved == 2


def test_cart_rejects_more_than_available_stock(client, db):
    product = add_product(db, stock=1)
    response = client.put(
        "/api/v1/cart/items",
        json={"variant_id": str(product.variants[0].id), "quantity": 2},
    )
    assert response.status_code == 409


def test_unsupported_shipping_country_is_rejected(client, db):
    product = add_product(db)
    client.put(
        "/api/v1/cart/items",
        json={"variant_id": str(product.variants[0].id), "quantity": 1},
    )
    response = client.post(
        "/api/v1/checkout",
        json={
            "email": "guest@example.com",
            "shipping_address": {
                "recipient_name": "Guest",
                "line1": "1 Tea Street",
                "city": "Paris",
                "postal_code": "75001",
                "country_code": "FR",
            },
        },
    )
    assert response.status_code == 422
