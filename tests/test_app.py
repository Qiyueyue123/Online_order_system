import sqlite3
from io import BytesIO
from pathlib import Path

import pytest

from app import create_app
from app.db import get_db, get_homepage_alert, get_menu_items, get_order, get_product_with_images, get_site_settings, hash_admin_password, init_db, list_pickup_days, list_stock_pools
from app.routes import ADMIN_LOGIN_FAILURES, build_pickup_slot_choices
from werkzeug.security import generate_password_hash

from conftest import CsrfTestClient, extract_csrf_token


def build_test_app(tmp_path):
    ADMIN_LOGIN_FAILURES.clear()
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SECRET_KEY": "test-secret-key",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": hash_admin_password("test-admin-password"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "MANUAL_ORDER_ONLY": False,
            "CAFE_CONTACT_PHONE": "@notqiyue",
            "CAFE_WHATSAPP_PHONE": "+6597888146",
        }
    )
    app.test_client_class = CsrfTestClient
    with app.app_context():
        init_db()
    return app


def first_pickup_value(app):
    with app.app_context():
        return build_pickup_slot_choices()[0]["value"]


def test_home_page_loads(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Authentic Japanese matcha, whisked fresh for pickup." in response.data
    assert b"Hello! We are Qiyue and Yuxun from Singapore" in response.data
    assert b"8 Jun - 16 Jun 2026" in response.data
    assert b"No fixed timing" in response.data
    assert b"We whisk 1g matcha with 10ml water or oat" in response.data
    assert b"temporary website link may change" in response.data
    assert b"Details" in response.data
    assert b"WhatsApp or Telegram for orders and questions" in response.data
    assert b"class=\"home-shell\"" in response.data
    assert b"/static/images/homepage-matcha-cup.jpg" in response.data
    assert b"/static/images/homepage-matcha-pour.mp4" in response.data
    assert b"class=\"home-showcase-image\"" in response.data
    assert b"data-carousel" in response.data
    assert b"data-lightbox-trigger" in response.data
    assert b"data-lightbox-prev" in response.data
    assert b"data-lightbox-next" in response.data
    assert b"Show previous photo for Ikuyo Matcha Latte" in response.data


def test_cloudflare_analytics_beacon_is_allowed(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]

    assert b"https://static.cloudflareinsights.com/beacon.min.js" in response.data
    assert "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com" in csp
    assert "connect-src 'self' https://cloudflareinsights.com" in csp


def test_home_page_can_use_manual_order_mode(tmp_path):
    app = build_test_app(tmp_path)
    app.config["MANUAL_ORDER_ONLY"] = True
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Choose chat" in response.data
    assert b"Message template" in response.data
    assert b"Copy order template" in response.data
    assert b"Order on WhatsApp" in response.data
    assert b"Order on Telegram" in response.data
    assert b"wa.me/6597888146" in response.data
    assert b"t.me/notqiyue" in response.data
    assert b"Drink:" in response.data
    assert b"Checkout" not in response.data


def test_default_menu_prices_match_sale_prices(tmp_path):
    app = build_test_app(tmp_path)

    with app.app_context():
        prices = {
            item["name"]: float(item["price_eur"])
            for item in get_menu_items()
        }

    assert prices["Ikuyo Matcha Latte"] == 3.9
    assert prices["Sayaka Matcha Latte"] == 5.9


def test_drink_detail_page_loads(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/drinks/1")

    assert response.status_code == 200
    assert b"Ikuyo Matcha Latte" in response.data
    assert b"carousel" in response.data
    assert b"Click the drink image to open the full uncropped photo." in response.data


def test_checkout_uses_circular_quantity_choices(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/checkout")

    assert response.status_code == 200
    assert b"class=\"quantity-picker\"" in response.data
    assert b"value=\"3\"" in response.data
    assert b"Tikkie payment request" in response.data
    assert b"we manually send a payment request link" in response.data


def test_sale_info_page_loads(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/sale-info")

    assert response.status_code == 200
    assert b"Sale info" in response.data
    assert b"Allergens" in response.data
    assert b"Privacy" in response.data
    assert b"Haarweg 333 Block C 053" in response.data


def test_checkout_creates_an_order(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "+65 12345678",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "2",
            "preparation_style_1": "oat",
            "extra_syrup_g_1": "1",
            "milk_adjustment_ml_1": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order #1 received" in response.data
    assert b"Whisk with oat milk" in response.data
    assert b"Agave syrup: 5g" in response.data
    assert b"Milk/oat base: 130ml" in response.data
    assert b"plastic cup and lid" in response.data
    assert b"Contact:" in response.data
    assert b"+65 12345678" in response.data
    assert b"Save this link for cancellation" in response.data
    assert b"Cancellation link" in response.data
    assert b"/orders/1/manage/" in response.data
    assert b"Manage or cancel order" in response.data

    with app.app_context():
        order_bundle = get_order(1)
        assert order_bundle["items"][0]["preparation_style"] == "oat"
        assert order_bundle["items"][0]["extra_syrup_g"] == 1
        assert order_bundle["items"][0]["milk_adjustment_ml"] == 10


def test_checkout_can_use_tikkie_payment_request(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "manual_tikkie",
            "quantity_1": "1",
            "preparation_style_1": "water",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Tikkie payment request" in response.data
    assert b"We will send a Tikkie payment request link" in response.data

    with app.app_context():
        order_bundle = get_order(1)
        assert order_bundle["order"]["payment_method"] == "manual_tikkie"


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
    assert b"Current live orders" in response.data
    assert b"Cancelled and past records" in response.data


def test_admin_login_accepts_legacy_werkzeug_hashes(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "legacy-admin.db"),
            "SECRET_KEY": "test-secret-key",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-password"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )
    app.test_client_class = CsrfTestClient
    client = app.test_client()

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Incoming orders" in response.data


def test_admin_login_rate_limits_failed_attempts(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    for _index in range(8):
        response = client.post(
            "/admin/login",
            data={"username": "admin", "password": "wrong-password"},
        )
        assert response.status_code == 200

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 429
    assert b"Too many failed login attempts" in response.data


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
            "image_file": (BytesIO(b"fake png bytes"), "new-image.png"),
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


def test_admin_can_update_site_contact(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-contact",
        data={
            "contact_line": "Whatsapp or Telegram: +65 90000000",
            "contact_phone": "+6590000000",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Contact details updated." in response.data

    with app.app_context():
        settings = get_site_settings()
        assert settings["contact_line"] == "Whatsapp or Telegram: +65 90000000"
        assert settings["contact_phone"] == "+6590000000"

    home_response = client.get("/")
    assert b"Whatsapp or Telegram: +65 90000000" in home_response.data
    assert b"href=\"tel:+6590000000\"" in home_response.data


def test_admin_can_upload_homepage_image(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Custom homepage matcha photo",
            "image_file": (BytesIO(b"fake png bytes"), "homepage.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage image added." in response.data

    with app.app_context():
        settings = get_site_settings()
        homepage_image = settings["homepage_images"][0]
        assert homepage_image["image_path"].startswith("/uploads/")
        assert homepage_image["alt_text"] == "Custom homepage matcha photo"
        saved_name = Path(homepage_image["image_path"]).name
        assert (Path(app.config["UPLOAD_FOLDER"]) / saved_name).exists()

    home_response = client.get("/")
    assert b"Custom homepage matcha photo" in home_response.data
    assert b"/uploads/" in home_response.data


def test_admin_can_upload_homepage_gif(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    gif_bytes = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
        b"\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
        b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    response = client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Homepage matcha GIF",
            "image_file": (BytesIO(gif_bytes), "homepage.gif"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage image added." in response.data

    with app.app_context():
        settings = get_site_settings()
        homepage_image = settings["homepage_images"][0]
        assert homepage_image["image_path"].endswith(".gif")
        assert homepage_image["alt_text"] == "Homepage matcha GIF"

    home_response = client.get("/")
    assert b"Homepage matcha GIF" in home_response.data
    assert b".gif" in home_response.data


def test_admin_can_upload_homepage_mp4(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Homepage matcha video",
            "image_file": (BytesIO(b"fake mp4 bytes"), "homepage.mp4"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage image added." in response.data

    with app.app_context():
        settings = get_site_settings()
        homepage_image = settings["homepage_images"][0]
        assert homepage_image["image_path"].endswith(".mp4")
        assert homepage_image["alt_text"] == "Homepage matcha video"

    home_response = client.get("/")
    assert b"Homepage matcha video" in home_response.data
    assert b"<video" in home_response.data
    assert b"data-carousel-video" in home_response.data
    assert b".mp4" in home_response.data


def test_admin_rejects_heif_homepage_upload_disguised_as_jpg(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    heif_like_bytes = b"\x00\x00\x00\x18ftypheic" + (b"0" * 64)
    response = client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Broken disguised upload",
            "image_file": (BytesIO(heif_like_bytes), "homepage.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"HEIC or HEIF images must be converted" in response.data

    with app.app_context():
        settings = get_site_settings()
        assert len(settings["homepage_images"]) == 3
        assert settings["homepage_images"][0]["id"] is None


def test_admin_can_reorder_homepage_images(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )
    client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Homepage photo 1",
            "image_file": (BytesIO(b"fake png bytes"), "homepage-1.png"),
        },
        content_type="multipart/form-data",
    )
    client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Homepage photo 2",
            "image_file": (BytesIO(b"fake png bytes"), "homepage-2.png"),
        },
        content_type="multipart/form-data",
    )

    with app.app_context():
        settings = get_site_settings()
        first_image_id = settings["homepage_images"][0]["id"]
        second_image_id = settings["homepage_images"][1]["id"]

    response = client.post(
        "/admin/site-homepage-images/order",
        data={
            f"sort_order_{first_image_id}": "2",
            f"sort_order_{second_image_id}": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage image order updated." in response.data

    with app.app_context():
        settings = get_site_settings()
        assert settings["homepage_images"][0]["id"] == second_image_id


def test_admin_can_reset_homepage_image_to_default(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )
    client.post(
        "/admin/site-homepage-image",
        data={
            "alt_text": "Temporary homepage image",
            "image_file": (BytesIO(b"fake png bytes"), "homepage.png"),
        },
        content_type="multipart/form-data",
    )

    with app.app_context():
        settings = get_site_settings()
        saved_name = Path(settings["homepage_images"][0]["image_path"]).name

    response = client.post(
        "/admin/site-homepage-images/clear",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Homepage images reset to default." in response.data

    with app.app_context():
        settings = get_site_settings()
        assert len(settings["homepage_images"]) == 3
        assert settings["homepage_images"][0]["id"] is None

    assert not (Path(app.config["UPLOAD_FOLDER"]) / saved_name).exists()

    home_response = client.get("/")
    assert b"/static/images/homepage-matcha-cup.jpg" in home_response.data


def test_footer_telegram_handle_is_clickable(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-contact",
        data={
            "contact_line": "Telegram:",
            "contact_phone": "@matchaorders",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    home_response = client.get("/")
    assert b"@matchaorders" in home_response.data
    assert b"href=\"https://t.me/matchaorders\"" in home_response.data


def test_footer_telegram_url_is_clickable(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/site-contact",
        data={
            "contact_line": "Telegram:",
            "contact_phone": "t.me/matchaorders",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    home_response = client.get("/")
    assert b"href=\"https://t.me/matchaorders\"" in home_response.data


def test_admin_can_update_pickup_availability(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    with app.app_context():
        pickup_day = list_pickup_days(days=1)[0]

    response = client.post(
        f"/admin/pickup-days/{pickup_day['id']}",
        data={
            "start_time": "18:00",
            "end_time": "20:00",
            "slot_capacity": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Pickup availability updated." in response.data

    with app.app_context():
        updated_day = list_pickup_days(days=1)[0]
        assert updated_day["is_available"] == 0
        assert updated_day["start_time"] == "18:00"
        assert updated_day["end_time"] == "20:00"
        assert updated_day["slot_capacity"] == 1

        assert all(
            not slot["value"].startswith(updated_day["pickup_date"])
            for slot in build_pickup_slot_choices()
        )


def test_admin_can_cancel_order(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "2",
            "preparation_style_1": "oat",
        },
    )

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/orders/1/cancel",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order cancelled and stock restored." in response.data

    with app.app_context():
        order_bundle = get_order(1)
        assert order_bundle["order"]["status"] == "cancelled"
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 25


def test_admin_can_mark_order_paid_and_collected(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "manual_tikkie",
            "quantity_1": "1",
            "preparation_style_1": "water",
        },
    )
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    paid_response = client.post(
        "/admin/orders/1/status",
        data={"status": "paid"},
        follow_redirects=True,
    )

    assert paid_response.status_code == 200
    assert b"Paid" in paid_response.data

    collected_response = client.post(
        "/admin/orders/1/status",
        data={"status": "collected"},
        follow_redirects=True,
    )

    assert collected_response.status_code == 200
    assert b"Collected" in collected_response.data

    with app.app_context():
        order_bundle = get_order(1)
        assert order_bundle["order"]["status"] == "collected"


def test_admin_can_delete_cancelled_order_record(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "oat",
        },
    )

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )
    client.post("/admin/orders/1/cancel")

    response = client.post(
        "/admin/orders/1/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order record deleted." in response.data

    with app.app_context():
        assert get_order(1) is None
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 25


def test_admin_cannot_delete_live_order_record(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "oat",
        },
    )

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/orders/1/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Only cancelled or past orders can be deleted." in response.data

    with app.app_context():
        assert get_order(1) is not None
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 24


def test_admin_can_delete_past_order_record_without_restoring_stock(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "oat",
        },
    )

    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE orders SET pickup_at = '2000-01-01T12:00' WHERE id = 1"
        )
        db.commit()

    client.post(
        "/admin/login",
        data={"username": "admin", "password": "test-admin-password"},
    )

    response = client.post(
        "/admin/orders/1/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order record deleted." in response.data

    with app.app_context():
        assert get_order(1) is None
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 24


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
                customer_contact="+65 12345678",
                pickup_at=build_pickup_slot_choices()[0]["value"],
                payment_method="cash",
                notes="",
                items={
                    1: {"quantity": 26, "preparation_style": "water"},
                },
            )
        except InventoryError as exc:
            assert "Not enough Ikuyo stock left" in str(exc)
        else:
            raise AssertionError("Expected InventoryError for overselling shared stock.")


def test_customer_can_cancel_order_with_private_link(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "+65 12345678",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "2",
            "preparation_style_1": "oat",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    confirmation_url = response.headers["Location"]
    assert "token=" in confirmation_url
    token = confirmation_url.split("token=", 1)[1]

    manage_response = client.get(f"/orders/1/manage/{token}")
    assert manage_response.status_code == 200
    assert b"Cancel order" in manage_response.data

    cancel_response = client.post(
        f"/orders/1/cancel/{token}",
        follow_redirects=True,
    )

    assert cancel_response.status_code == 200
    assert b"Order cancelled" in cancel_response.data

    with app.app_context():
        order_bundle = get_order(1)
        assert order_bundle["order"]["status"] == "cancelled"
        stock_pools = list_stock_pools()
        assert stock_pools[0]["servings_available"] == 25


def test_customer_cannot_manage_order_with_wrong_token(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()

    client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "@qy",
            "pickup_at": first_pickup_value(app),
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "water",
        },
    )

    response = client.get("/orders/1/manage/wrong-token")

    assert response.status_code == 404


def test_hash_password_cli_command_outputs_a_hash(tmp_path):
    app = build_test_app(tmp_path)
    runner = app.test_cli_runner()

    result = runner.invoke(args=["hash-password", "fresh-password"])

    assert result.exit_code == 0
    assert result.output.strip().startswith("$argon2id$")


def test_init_db_migrates_existing_site_settings_table(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "legacy.db"),
            "SECRET_KEY": "test-secret-key",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-password"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )

    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE IF EXISTS site_settings")
        db.execute(
            """
            CREATE TABLE site_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                homepage_alert TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO site_settings (id, homepage_alert)
            VALUES (1, 'Legacy alert')
            """
        )
        db.commit()

        init_db()

        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(site_settings)").fetchall()
        }
        homepage_images_table = db.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'homepage_images'
            """
        ).fetchone()
        settings = get_site_settings()

        assert "contact_line" in columns
        assert "contact_phone" in columns
        assert "homepage_image_path" in columns
        assert "homepage_image_alt" in columns
        assert homepage_images_table is not None
        assert settings["homepage_alert"] == "Legacy alert"


def test_checkout_post_without_csrf_token_is_rejected(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "+65 12345678",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "water",
        },
        csrf=False,
    )

    assert response.status_code == 400

    with app.app_context():
        assert get_order(1) is None


def test_checkout_post_with_token_scraped_from_rendered_page_succeeds(tmp_path):
    app = build_test_app(tmp_path)
    client = app.test_client()
    pickup_value = first_pickup_value(app)

    checkout_page = client.get("/checkout")
    csrf_token = extract_csrf_token(checkout_page.data)

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Qy",
            "customer_contact": "+65 12345678",
            "pickup_at": pickup_value,
            "payment_method": "cash",
            "quantity_1": "1",
            "preparation_style_1": "water",
            "_csrf_token": csrf_token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Order #1 received" in response.data


def test_pickup_slot_rejects_order_once_capacity_is_reached(tmp_path):
    app = build_test_app(tmp_path)
    from app.db import SlotCapacityError, create_order

    with app.app_context():
        pickup_value = build_pickup_slot_choices()[0]["value"]
        pickup_day = list_pickup_days(days=1)[0]
        slot_capacity = pickup_day["slot_capacity"]
        assert slot_capacity == 2

        # Fill the slot up to (and including) its capacity: these must succeed.
        for index in range(slot_capacity):
            result = create_order(
                name=f"Customer {index}",
                customer_contact=f"+65 1000000{index}",
                pickup_at=pickup_value,
                payment_method="cash",
                notes="",
                items={1: {"quantity": 1, "preparation_style": "water"}},
            )
            assert result["order_id"] is not None

        # The next order for the same slot must be rejected once it's full.
        with pytest.raises(SlotCapacityError):
            create_order(
                name="One too many",
                customer_contact="+65 19999999",
                pickup_at=pickup_value,
                payment_method="cash",
                notes="",
                items={1: {"quantity": 1, "preparation_style": "water"}},
            )


def test_pickup_slot_accepts_orders_up_to_capacity_minus_one(tmp_path):
    app = build_test_app(tmp_path)
    from app.db import create_order

    with app.app_context():
        pickup_value = build_pickup_slot_choices()[0]["value"]
        pickup_day = list_pickup_days(days=1)[0]
        slot_capacity = pickup_day["slot_capacity"]
        assert slot_capacity == 2

        for index in range(slot_capacity - 1):
            result = create_order(
                name=f"Customer {index}",
                customer_contact=f"+65 1000000{index}",
                pickup_at=pickup_value,
                payment_method="cash",
                notes="",
                items={1: {"quantity": 1, "preparation_style": "water"}},
            )
            assert result["order_id"] is not None

        # Still one seat left in the slot, so this booking must succeed.
        remaining_slots = build_pickup_slot_choices()
        matching_slot = next(
            slot for slot in remaining_slots if slot["value"] == pickup_value
        )
        assert matching_slot["remaining_capacity"] == 1


def test_foreign_key_violation_is_rejected(tmp_path):
    app = build_test_app(tmp_path)

    with app.app_context():
        db = get_db()
        fk_status = db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_status == 1

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO product_images (product_id, image_path, alt_text, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (999999, "/static/images/orphan.png", "orphan image", 1),
            )


def test_seed_inventory_handles_legacy_site_settings_table(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "legacy-seed.db"),
            "SECRET_KEY": "test-secret-key",
            "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD_HASH": generate_password_hash("test-admin-password"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )

    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE IF EXISTS site_settings")
        db.execute(
            """
            CREATE TABLE site_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                homepage_alert TEXT,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()

        from app.db import _seed_inventory

        _seed_inventory(db)

        row = db.execute("SELECT id, homepage_alert FROM site_settings WHERE id = 1").fetchone()
        assert row["id"] == 1
