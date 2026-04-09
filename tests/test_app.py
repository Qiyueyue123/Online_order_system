from io import BytesIO

from app import create_app
from app.db import get_homepage_alert, get_menu_items, get_product_with_images, init_db, list_stock_pools
from app.routes import build_pickup_slot_choices
from werkzeug.security import generate_password_hash


def build_test_app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SECRET_KEY": "test-secret-key",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-password"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )
    with app.app_context():
        init_db()
    return app


def test_home_page_loads(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Matcha pickup menu" in response.data
    assert b"Open full drink page" in response.data
    assert b"data-carousel" in response.data
    assert b"data-lightbox-trigger" in response.data
    assert b"Show previous photo for Ikuyo Matcha Latte" in response.data


def test_drink_detail_page_loads(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/drinks/1")

    assert response.status_code == 200
    assert b"Ikuyo Matcha Latte" in response.data
    assert b"carousel" in response.data
    assert b"Click the drink image to open the full uncropped photo." in response.data


def test_checkout_creates_an_order(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = build_pickup_slot_choices()[0]["value"]

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "phone_last4": "5678",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "2",
            "preparation_style_1": "type_2",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order #1 received" in response.data
    assert b"Type 2" in response.data
    assert b"Phone ending:" in response.data


def test_admin_login_required(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/admin")

    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]


def test_admin_login_works(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Incoming orders" in response.data


def test_admin_can_upload_product_image(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/products/1/images",
        data={
            "alt_text": "Uploaded Ikuyo image",
            "image_file": (BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"), "new-image.svg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Uploaded Ikuyo image" in response.data


def test_admin_can_reorder_product_images(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    with app.app_context():
        product_bundle = get_product_with_images(1)
        first_image_id = product_bundle["images"][0]["id"]
        second_image_id = product_bundle["images"][1]["id"]

    response = client.post(
        "/admin/products/1/images/order",
        data={
            f"sort_order_{first_image_id}": "2",
            f"sort_order_{second_image_id}": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Image order updated." in response.data

    with app.app_context():
        reordered_bundle = get_product_with_images(1)
        assert reordered_bundle["images"][0]["id"] == second_image_id


def test_admin_can_update_stock(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/stock-pools/1",
        data={"servings_available": "18", "grams_per_serving": "5"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Stock updated." in response.data

    with app.app_context():
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 18
        assert stock_pools[0]["grams_per_serving"] == 5


def test_admin_can_update_homepage_alert(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-alert",
        data={"homepage_alert": "Collections paused after 8pm."},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage alert updated." in response.data

    with app.app_context():
        assert get_homepage_alert() == "Collections paused after 8pm."

    home_response = client.get("/")
    assert b"Collections paused after 8pm." in home_response.data


def test_admin_can_delete_product_image(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    with app.app_context():
        product_bundle = get_product_with_images(1)
        image_id = product_bundle["images"][0]["id"]
        initial_count = len(product_bundle["images"])

    response = client.post(
        f"/admin/images/{image_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Image deleted." in response.data

    with app.app_context():
        updated_bundle = get_product_with_images(1)
        assert len(updated_bundle["images"]) == initial_count - 1


def test_admin_can_create_update_and_delete_product(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    create_response = client.post(
        "/admin/products",
        data={
            "name": "Trial Drink",
            "price_eur": "6.20",
            "description": "Small batch test drink.",
            "stock_pool_id": "1",
        },
        follow_redirects=True,
    )

    assert create_response.status_code == 200
    assert b"Drink created." in create_response.data

    with app.app_context():
        products = get_menu_items()
        created_product = next(product for product in products if product["name"] == "Trial Drink")
        created_product_id = created_product["id"]

    update_response = client.post(
        f"/admin/products/{created_product_id}",
        data={
            "name": "Updated Trial Drink",
            "price_eur": "6.80",
            "description": "Updated drink description.",
            "stock_pool_id": "2",
        },
        follow_redirects=True,
    )

    assert update_response.status_code == 200
    assert b"Drink updated." in update_response.data

    with app.app_context():
        products = get_menu_items()
        updated_product = next(product for product in products if product["id"] == created_product_id)
        assert updated_product["name"] == "Updated Trial Drink"
        assert float(updated_product["price_eur"]) == 6.8
        assert updated_product["stock_pool_name"] == "Sayaka"

    delete_response = client.post(
        f"/admin/products/{created_product_id}/delete",
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    assert b"Drink deleted." in delete_response.data

    with app.app_context():
        products = get_menu_items()
        assert all(product["id"] != created_product_id for product in products)


def test_shared_stock_pool_prevents_oversell(tmp_path):
    app = build_test_app(tmp_path)

    with app.app_context():
        try:
            app.config["TESTING"] = False
            from app.db import InventoryError, create_order

            create_order(
                name="Qy",
                phone_last4="5678",
                pickup_at=build_pickup_slot_choices()[0]["value"],
                payment_method="cash",
                notes="",
                items={
                    1: {"quantity": 20, "preparation_style": "type_1"},
                    2: {"quantity": 6, "preparation_style": "type_2"},
                },
            )
        except InventoryError as exc:
            assert "Not enough Ikuyo stock left" in str(exc)
        else:
            raise AssertionError("Expected InventoryError for overselling shared stock.")


def test_hash_password_cli_command_outputs_a_hash(tmp_path):
    app = build_test_app(tmp_path)
    runner = app.test_cli_runner()

    result = runner.invoke(args=["hash-password", "fresh-password"])

    assert result.exit_code == 0
    assert result.output.strip().startswith("scrypt:")
