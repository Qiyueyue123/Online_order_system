import os

from flask import Flask

from .db import get_site_settings, init_app, init_db, sync_admin_user_from_config


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
        }

    from .routes import bp

    app.register_blueprint(bp)
    return app
