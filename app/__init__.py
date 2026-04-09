import os

from flask import Flask

from .db import init_app, init_db, sync_admin_user_from_config


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

    from .routes import bp

    app.register_blueprint(bp)
    return app
