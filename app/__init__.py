import os
import re
import secrets
from datetime import timedelta
from urllib.parse import quote

from flask import Flask, abort, request, session
from markupsafe import Markup

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
    is_debug = os.environ.get("FLASK_DEBUG") == "1"
    default_admin_password = (
        "change-me-admin" if is_debug else None
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
        SESSION_COOKIE_SECURE=os.environ.get(
            "SESSION_COOKIE_SECURE",
            "0" if is_debug else "1",
        ) == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )

    if test_config is not None:
        app.config.update(test_config)

    if (
        not app.config.get("TESTING")
        and not is_debug
        and app.config["SECRET_KEY"] == "dev-secret-key"
    ):
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_app(app)

    with app.app_context():
        init_db()
        sync_admin_user_from_config()

    def get_csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    def csrf_field():
        return Markup(
            '<input name="_csrf_token" type="hidden" value="{}">'.format(
                get_csrf_token(),
            )
        )

    @app.before_request
    def validate_csrf_token():
        if request.method != "POST" or app.config.get("TESTING"):
            return
        expected_token = session.get("_csrf_token")
        submitted_token = request.form.get("_csrf_token") or request.headers.get(
            "X-CSRF-Token",
        )
        if not expected_token or not secrets.compare_digest(
            expected_token,
            submitted_token or "",
        ):
            abort(400)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "media-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "form-action 'self'",
        )
        return response

    @app.context_processor
    def inject_site_contact():
        settings = get_site_settings()
        return {
            "cafe_contact_line": settings["contact_line"],
            "cafe_contact_phone": settings["contact_phone"],
            "cafe_contact_link": build_contact_link_target(settings["contact_phone"]),
            "csrf_token": get_csrf_token,
            "csrf_field": csrf_field,
        }

    from .routes import bp

    app.register_blueprint(bp)
    return app
