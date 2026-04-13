import os
import re
from urllib.parse import quote

from flask import Flask

from .db import get_site_settings, init_app, init_db, sync_admin_user_from_config


def build_contact_link_target(value):
    if not value:
        return None

    contact = value.strip()
    lowered = contact.lower()
    if lowered.startswith(("http://", "https://", "tel:", "mailto:")):
        return contact
    if lowered.startswith("t.me/"):
        return f"https://{contact}"
    if lowered.startswith("@") and len(contact) > 1:
        return f"https://t.me/{quote(contact[1:])}"
    if lowered.startswith("telegram:"):
        handle = contact.split(":", 1)[1].strip().lstrip("@")
        return f"https://t.me/{quote(handle)}" if handle else None
    if lowered.startswith("whatsapp:"):
        phone = re.sub(r"\D", "", contact.split(":", 1)[1])
        return f"https://wa.me/{phone}" if phone else None

    digits = re.sub(r"\D", "", contact)
    if digits:
        phone_href = contact if contact.startswith("+") else f"+{digits}"
        return f"tel:{phone_href}"
    return None


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    default_admin_password = (
        "change-me-admin" if os.environ.get("FLASK_DEBUG") == "1" else None
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
        DATABASE=os.environ.get(
            "DATABASE_PATH",
            os.path.join(app.instance_path, "matcha.db"),
        ),
        UPLOAD_FOLDER=os.environ.get(
            "UPLOAD_FOLDER",
            os.path.join(app.instance_path, "uploads"),
        ),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", default_admin_password),
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH"),
        CAFE_CONTACT_LINE=os.environ.get(
            "CAFE_CONTACT_LINE",
            "Whatsapp/Telegram for any query: +65 97888146",
        ),
        CAFE_CONTACT_PHONE=os.environ.get("CAFE_CONTACT_PHONE", "+6597888146"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_app(app)

    with app.app_context():
        init_db()
        sync_admin_user_from_config()

    @app.context_processor
    def inject_site_contact():
        settings = get_site_settings()
        return {
            "cafe_contact_line": settings["contact_line"],
            "cafe_contact_phone": settings["contact_phone"],
            "cafe_contact_link": build_contact_link_target(settings["contact_phone"]),
        }

    from .routes import bp

    app.register_blueprint(bp)
    return app
