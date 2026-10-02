from conftest import add_product, put_item


def test_view_empty_cart(client):
    response = client.get("/api/v1/cart")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_add_item_then_view_cart(client, db):
    product = add_product(db)
    put_item(client, product.variants[0], quantity=2)

    cart = client.get("/api/v1/cart").json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2
    assert cart["items"][0]["id"]


def test_remove_item_from_cart(client, db):
    product = add_product(db)
    put_item(client, product.variants[0], quantity=1)
    item_id = client.get("/api/v1/cart").json()["items"][0]["id"]

    response = client.delete(f"/api/v1/cart/items/{item_id}")
    assert response.status_code == 200
    assert response.json()["items"] == []

    cart = client.get("/api/v1/cart").json()
    assert cart["items"] == []


def test_remove_unknown_item_is_404(client, db):
    add_product(db)
    response = client.delete("/api/v1/cart/items/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_remove_item_does_not_touch_other_carts(client, db):
    product = add_product(db)
    put_item(client, product.variants[0], quantity=1)
    item_id = client.get("/api/v1/cart").json()["items"][0]["id"]

    # Dropping the cart cookie simulates a second, unrelated guest: they get a
    # brand new cart and must not be able to delete the first guest's line.
    client.cookies.clear()
    response = client.delete(f"/api/v1/cart/items/{item_id}")
    assert response.status_code == 404
