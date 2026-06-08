import secrets
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta

import click
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash


SEED_STOCK_POOLS = [
    ("Ikuyo", 25, 4),
    ("Sayaka", 5, 4),
]

RETIRED_PRODUCT_NAMES = {
    "Strawberry Ikuyo Matcha Latte",
}

SEED_MENU = [
    (
        "Ikuyo Matcha Latte",
        3.90,
        "Ippodo Ikuyo with regular full cream milk.",
        "Ikuyo",
    ),
    (
        "Sayaka Matcha Latte",
        5.90,
        "Ippodo Sayaka, an elevated matcha line from Ippodo with a smoother, richer profile, served with regular full cream milk.",
        "Sayaka",
    ),
]

UPDATED_PRODUCT_PRICES = {
    "Ikuyo Matcha Latte": {
        "old": (4.00,),
        "new": 3.90,
    },
    "Sayaka Matcha Latte": {
        "old": (5.00,),
        "new": 5.90,
    },
}

UPDATED_PRODUCT_DESCRIPTIONS = {
    "Ikuyo Matcha Latte": {
        "old": "Ippodo Ikuyo with low-fat milk.",
        "new": "Ippodo Ikuyo with regular full cream milk.",
    },
    "Sayaka Matcha Latte": {
        "old": (
            "Ippodo Sayaka with low-fat milk.",
            "Ippodo Sayaka with regular full cream milk.",
        ),
        "new": "Ippodo Sayaka, an elevated matcha line from Ippodo with a smoother, richer profile, served with regular full cream milk.",
    },
}

SEED_PRODUCT_IMAGES = {
    "Ikuyo Matcha Latte": [
        (
            "/static/images/ikuyo-latte-real-1.webp",
            "Ikuyo matcha latte in cup",
            1,
        ),
        (
            "/static/images/ikuyo-latte-real-2.png",
            "Ikuyo matcha latte close-up",
            2,
        ),
    ],
    "Sayaka Matcha Latte": [
        (
            "/static/images/sayaka-latte-real-1.webp",
            "Sayaka matcha latte in cup",
            1,
        ),
        (
            "/static/images/sayaka-latte-real-2.png",
            "Sayaka matcha latte close-up",
            2,
        ),
    ],
}

SEED_HOMEPAGE_IMAGES = [
    (
        "/static/images/homepage-matcha-cup.jpg",
        "Fresh iced matcha latte for the cafe run",
        1,
    ),
    (
        "/static/images/homepage-matcha-pour.mp4",
        "Short video of matcha being prepared",
        2,
    ),
    (
        "/static/images/homepage-sayaka-latte.jpg",
        "Sayaka matcha latte served cold",
        3,
    ),
]

STATIC_IMAGE_REPLACEMENTS = {
    "/static/images/ikuyo-latte-1.svg": (
        "/static/images/ikuyo-latte-real-1.webp",
        "Ikuyo matcha latte in cup",
    ),
    "/static/images/ikuyo-latte-2.svg": (
        "/static/images/ikuyo-latte-real-2.png",
        "Ikuyo matcha latte close-up",
    ),
    "/static/images/sayaka-latte-1.svg": (
        "/static/images/sayaka-latte-real-1.webp",
        "Sayaka matcha latte in cup",
    ),
    "/static/images/sayaka-latte-2.svg": (
        "/static/images/sayaka-latte-real-2.png",
        "Sayaka matcha latte close-up",
    ),
}

PREPARATION_STYLES = {
    "water": "Whisk with water (standard)",
    "oat": "Whisk with oat milk for a frothier drink",
}

BASE_AGAVE_SYRUP_G = 4.0
BASE_REGULAR_MILK_ML = 120
MIN_SYRUP_ADJUSTMENT_G = -4.0
MAX_EXTRA_SYRUP_G = 5.0
MIN_MILK_ADJUSTMENT_ML = -30
MAX_MILK_ADJUSTMENT_ML = 30

ORDER_STATUSES = {
    "new": "New",
    "paid": "Paid",
    "collected": "Collected",
    "cancelled": "Cancelled",
}

ADMIN_PASSWORD_HASHER = PasswordHasher()


class InventoryError(ValueError):
    pass


def hash_admin_password(password):
    return ADMIN_PASSWORD_HASHER.hash(password)


def _is_argon2_hash(password_hash):
    return bool(password_hash) and password_hash.startswith("$argon2")


def verify_admin_password_hash(password_hash, password):
    if not password_hash:
        return False
    if _is_argon2_hash(password_hash):
        try:
            return ADMIN_PASSWORD_HASHER.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False
    return check_password_hash(password_hash, password)


def admin_password_hash_needs_upgrade(password_hash):
    if not password_hash:
        return False
    if not _is_argon2_hash(password_hash):
        return True
    try:
        return ADMIN_PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(__file__).with_name("schema.sql")
    db.executescript(schema_path.read_text())
    _migrate_schema(db)
    _seed_inventory(db)
    _seed_menu(db)
    _remove_unused_retired_products(db)
    _update_known_product_descriptions(db)
    _update_known_product_prices(db)
    _update_placeholder_contact_settings(db)
    _update_static_seed_image_paths(db)
    db.commit()


def sync_admin_user_from_config():
    db = get_db()
    username = current_app.config.get("ADMIN_USERNAME")
    raw_password = current_app.config.get("ADMIN_PASSWORD")
    password_hash = current_app.config.get("ADMIN_PASSWORD_HASH")

    if not username:
        return

    admin_user = db.execute(
        """
        SELECT id, username, password_hash
        FROM admin_users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()

    resolved_password_hash = None
    should_update_password = False

    if password_hash:
        if admin_user is None or admin_user["password_hash"] != password_hash:
            resolved_password_hash = password_hash
            should_update_password = True
    elif raw_password:
        if (
            admin_user is None
            or not verify_admin_password_hash(admin_user["password_hash"], raw_password)
            or admin_password_hash_needs_upgrade(admin_user["password_hash"])
        ):
            resolved_password_hash = hash_admin_password(raw_password)
            should_update_password = True

    if admin_user is None:
        if resolved_password_hash is None:
            raise RuntimeError("An admin password or password hash must be configured.")
        db.execute(
            """
            INSERT INTO admin_users (username, password_hash)
            VALUES (?, ?)
            """,
            (username, resolved_password_hash),
        )
        db.commit()
        return

    if should_update_password and resolved_password_hash is not None:
        db.execute(
            """
            UPDATE admin_users
            SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (resolved_password_hash, admin_user["id"]),
        )
        db.commit()


def reset_db():
    close_db()
    database_path = Path(current_app.config["DATABASE"])
    if database_path.exists():
        database_path.unlink()
    init_db()


def _table_columns(db, table_name):
    rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_schema(db):
    site_settings_columns = _table_columns(db, "site_settings")
    if "contact_line" not in site_settings_columns:
        db.execute("ALTER TABLE site_settings ADD COLUMN contact_line TEXT")
    if "contact_phone" not in site_settings_columns:
        db.execute("ALTER TABLE site_settings ADD COLUMN contact_phone TEXT")
    if "homepage_image_path" not in site_settings_columns:
        db.execute("ALTER TABLE site_settings ADD COLUMN homepage_image_path TEXT")
    if "homepage_image_alt" not in site_settings_columns:
        db.execute("ALTER TABLE site_settings ADD COLUMN homepage_image_alt TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS homepage_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            alt_text TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    legacy_homepage_image = db.execute(
        """
        SELECT homepage_image_path, homepage_image_alt
        FROM site_settings
        WHERE id = 1
        """
    ).fetchone()
    existing_homepage_image_count = db.execute(
        "SELECT COUNT(*) FROM homepage_images"
    ).fetchone()[0]
    if (
        legacy_homepage_image is not None
        and legacy_homepage_image["homepage_image_path"]
        and existing_homepage_image_count == 0
    ):
        db.execute(
            """
            INSERT INTO homepage_images (image_path, alt_text, sort_order)
            VALUES (?, ?, 1)
            """,
            (
                legacy_homepage_image["homepage_image_path"],
                legacy_homepage_image["homepage_image_alt"]
                or "Homepage matcha showcase image",
            ),
        )
        db.execute(
            """
            UPDATE site_settings
            SET homepage_image_path = NULL, homepage_image_alt = NULL
            WHERE id = 1
            """
        )

    order_columns = _table_columns(db, "orders")
    if "customer_contact" not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN customer_contact TEXT")
        if "phone_number" in order_columns:
            db.execute(
                """
                UPDATE orders
                SET customer_contact = phone_number
                WHERE customer_contact IS NULL
                """
            )
        elif "phone_last4" in order_columns:
            db.execute(
                """
                UPDATE orders
                SET customer_contact = 'Phone ending ' || phone_last4
                WHERE customer_contact IS NULL
                """
            )
    if "phone_last4" not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN phone_last4 TEXT")
        if "phone_number" in order_columns:
            db.execute(
                """
                UPDATE orders
                SET phone_last4 = substr(phone_number, -4)
                WHERE phone_last4 IS NULL
                """
            )
    if "pickup_at" not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN pickup_at TEXT")
        if "created_at" in order_columns:
            db.execute(
                """
                UPDATE orders
                SET pickup_at = strftime('%Y-%m-%dT%H:%M', created_at)
                WHERE pickup_at IS NULL
                """
            )
    if "cancel_token_hash" not in order_columns:
        db.execute("ALTER TABLE orders ADD COLUMN cancel_token_hash TEXT")

    order_item_columns = _table_columns(db, "order_items")
    if "syrup_level" not in order_item_columns:
        db.execute(
            "ALTER TABLE order_items ADD COLUMN syrup_level TEXT NOT NULL DEFAULT 'standard'"
        )
    if "milk_volume" not in order_item_columns:
        db.execute(
            "ALTER TABLE order_items ADD COLUMN milk_volume TEXT NOT NULL DEFAULT 'standard'"
        )
    if "extra_syrup_g" not in order_item_columns:
        db.execute(
            "ALTER TABLE order_items ADD COLUMN extra_syrup_g REAL NOT NULL DEFAULT 0"
        )
    if "milk_adjustment_ml" not in order_item_columns:
        db.execute(
            "ALTER TABLE order_items ADD COLUMN milk_adjustment_ml INTEGER NOT NULL DEFAULT 0"
        )


def ensure_pickup_days(reference_date=None, days=7):
    if reference_date is None:
        reference_date = date.today()

    db = get_db()
    for day_offset in range(days):
        pickup_date = reference_date + timedelta(days=day_offset)
        db.execute(
            """
            INSERT OR IGNORE INTO pickup_days (
                pickup_date,
                is_available,
                start_time,
                end_time,
                slot_capacity
            )
            VALUES (?, 1, '16:00', '21:00', 2)
            """,
            (pickup_date.isoformat(),),
        )
    db.commit()


def list_pickup_days(reference_date=None, days=7):
    if reference_date is None:
        reference_date = date.today()
    ensure_pickup_days(reference_date=reference_date, days=days)

    db = get_db()
    start_date = reference_date.isoformat()
    end_date = (reference_date + timedelta(days=days - 1)).isoformat()
    return db.execute(
        """
        SELECT id, pickup_date, is_available, start_time, end_time, slot_capacity
        FROM pickup_days
        WHERE pickup_date BETWEEN ? AND ?
        ORDER BY pickup_date
        """,
        (start_date, end_date),
    ).fetchall()


def update_pickup_day(pickup_day_id, is_available, start_time, end_time, slot_capacity):
    if start_time >= end_time:
        raise ValueError("Start time must be before end time.")
    if slot_capacity < 1:
        raise ValueError("Slot capacity must be at least 1.")

    db = get_db()
    cursor = db.execute(
        """
        UPDATE pickup_days
        SET
            is_available = ?,
            start_time = ?,
            end_time = ?,
            slot_capacity = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            1 if is_available else 0,
            start_time,
            end_time,
            slot_capacity,
            pickup_day_id,
        ),
    )
    if cursor.rowcount == 0:
        raise ValueError("Pickup day not found.")
    db.commit()


def get_active_order_counts_by_pickup_at():
    db = get_db()
    rows = db.execute(
        """
        SELECT pickup_at, COUNT(*) AS order_count
        FROM orders
        WHERE status != 'cancelled'
        GROUP BY pickup_at
        """
    ).fetchall()
    return {row["pickup_at"]: row["order_count"] for row in rows}


def extract_contact_suffix(contact):
    digits = "".join(char for char in contact if char.isdigit())
    if len(digits) >= 4:
        return digits[-4:]
    cleaned = contact.strip()
    if len(cleaned) >= 4:
        return cleaned[-4:]
    return cleaned or "----"


def _seed_inventory(db):
    site_settings_columns = _table_columns(db, "site_settings")
    if {
        "contact_line",
        "contact_phone",
        "homepage_image_path",
        "homepage_image_alt",
    }.issubset(site_settings_columns):
        db.execute(
            """
            INSERT OR IGNORE INTO site_settings (
                id,
                homepage_alert,
                homepage_image_path,
                homepage_image_alt,
                contact_line,
                contact_phone
            )
            VALUES (1, NULL, NULL, NULL, ?, ?)
            """,
            (
                current_app.config.get("CAFE_CONTACT_LINE"),
                current_app.config.get("CAFE_CONTACT_PHONE"),
            ),
        )
    else:
        db.execute(
            """
            INSERT OR IGNORE INTO site_settings (id, homepage_alert)
            VALUES (1, NULL)
            """
        )

    existing_count = db.execute("SELECT COUNT(*) FROM stock_pools").fetchone()[0]
    if existing_count:
        return

    db.executemany(
        """
        INSERT INTO stock_pools (name, servings_available, grams_per_serving)
        VALUES (?, ?, ?)
        """,
        SEED_STOCK_POOLS,
    )


def _seed_menu(db):
    existing_count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if existing_count:
        return

    for name, price_eur, description, stock_pool_name in SEED_MENU:
        stock_pool = db.execute(
            "SELECT id FROM stock_pools WHERE name = ?",
            (stock_pool_name,),
        ).fetchone()
        product_cursor = db.execute(
            """
            INSERT INTO products (name, price_eur, description, stock_pool_id)
            VALUES (?, ?, ?, ?)
            """,
            (name, price_eur, description, stock_pool["id"]),
        )
        product_id = product_cursor.lastrowid
        db.executemany(
            """
            INSERT INTO product_images (product_id, image_path, alt_text, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            [
                (product_id, image_path, alt_text, sort_order)
                for image_path, alt_text, sort_order in SEED_PRODUCT_IMAGES[name]
            ],
        )


def _update_static_seed_image_paths(db):
    for old_path, (new_path, alt_text) in STATIC_IMAGE_REPLACEMENTS.items():
        db.execute(
            """
            UPDATE product_images
            SET image_path = ?, alt_text = ?
            WHERE image_path = ?
            """,
            (new_path, alt_text, old_path),
        )


def _update_placeholder_contact_settings(db):
    db.execute(
        """
        UPDATE site_settings
        SET contact_line = ?, contact_phone = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
          AND (
            contact_phone IS NULL
            OR contact_phone = ''
            OR contact_phone = '@matchaorders'
          )
        """,
        (
            current_app.config.get("CAFE_CONTACT_LINE"),
            current_app.config.get("CAFE_CONTACT_PHONE"),
        ),
    )


def _remove_unused_retired_products(db):
    for product_name in RETIRED_PRODUCT_NAMES:
        product = db.execute(
            """
            SELECT id
            FROM products
            WHERE name = ?
            """,
            (product_name,),
        ).fetchone()
        if product is None:
            continue

        order_item_count = db.execute(
            """
            SELECT COUNT(*)
            FROM order_items
            WHERE product_id = ?
            """,
            (product["id"],),
        ).fetchone()[0]
        if order_item_count:
            continue

        db.execute(
            """
            DELETE FROM product_images
            WHERE product_id = ?
            """,
            (product["id"],),
        )
        db.execute(
            """
            DELETE FROM products
            WHERE id = ?
            """,
            (product["id"],),
        )


def _update_known_product_descriptions(db):
    for product_name, description_update in UPDATED_PRODUCT_DESCRIPTIONS.items():
        old_descriptions = description_update["old"]
        if isinstance(old_descriptions, str):
            old_descriptions = (old_descriptions,)
        placeholders = ", ".join("?" for _description in old_descriptions)
        db.execute(
            f"""
            UPDATE products
            SET description = ?
            WHERE name = ? AND description IN ({placeholders})
            """,
            (
                description_update["new"],
                product_name,
                *old_descriptions,
            ),
        )


def _update_known_product_prices(db):
    for product_name, price_update in UPDATED_PRODUCT_PRICES.items():
        placeholders = ", ".join("?" for _price in price_update["old"])
        db.execute(
            f"""
            UPDATE products
            SET price_eur = ?
            WHERE name = ? AND ROUND(price_eur, 2) IN ({placeholders})
            """,
            (
                price_update["new"],
                product_name,
                *price_update["old"],
            ),
        )


def get_menu_items():
    db = get_db()
    products = db.execute(
        """
        SELECT
            p.id,
            p.name,
            p.price_eur,
            p.description,
            sp.name AS stock_pool_name,
            sp.servings_available,
            sp.grams_per_serving
        FROM products p
        JOIN stock_pools sp ON sp.id = p.stock_pool_id
        ORDER BY p.id
        """
    ).fetchall()

    product_images = db.execute(
        """
        SELECT id, product_id, image_path, alt_text, sort_order
        FROM product_images
        ORDER BY product_id, sort_order, id
        """
    ).fetchall()

    images_by_product_id = {}
    for image in product_images:
        images_by_product_id.setdefault(image["product_id"], []).append(dict(image))

    enriched_products = []
    for product in products:
        product_dict = dict(product)
        product_dict["images"] = images_by_product_id.get(product["id"], [])
        product_dict["cover_image_path"] = (
            product_dict["images"][0]["image_path"]
            if product_dict["images"]
            else None
        )
        enriched_products.append(product_dict)
    return enriched_products


def get_preparation_style_choices():
    return PREPARATION_STYLES


def get_recipe_defaults():
    return {
        "base_agave_syrup_g": BASE_AGAVE_SYRUP_G,
        "base_regular_milk_ml": BASE_REGULAR_MILK_ML,
        "min_syrup_adjustment_g": MIN_SYRUP_ADJUSTMENT_G,
        "max_extra_syrup_g": MAX_EXTRA_SYRUP_G,
        "min_milk_adjustment_ml": MIN_MILK_ADJUSTMENT_ML,
        "max_milk_adjustment_ml": MAX_MILK_ADJUSTMENT_ML,
    }


def get_site_settings():
    db = get_db()
    row = db.execute(
        """
        SELECT homepage_alert, homepage_image_path, homepage_image_alt, contact_line, contact_phone
        FROM site_settings
        WHERE id = 1
        """
    ).fetchone()
    defaults = {
        "homepage_alert": None,
        "homepage_image_path": None,
        "homepage_image_alt": "Photo of the ceremonial matcha used for this cafe run",
        "contact_line": current_app.config.get("CAFE_CONTACT_LINE"),
        "contact_phone": current_app.config.get("CAFE_CONTACT_PHONE"),
    }
    if row is None:
        return defaults

    settings = dict(row)
    settings["homepage_image_path"] = settings["homepage_image_path"] or defaults["homepage_image_path"]
    settings["homepage_image_alt"] = settings["homepage_image_alt"] or defaults["homepage_image_alt"]
    settings["contact_line"] = settings["contact_line"] or defaults["contact_line"]
    settings["contact_phone"] = settings["contact_phone"] or defaults["contact_phone"]
    settings["homepage_images"] = get_homepage_images()
    return settings


def get_homepage_alert():
    return get_site_settings()["homepage_alert"]


def update_homepage_alert(message):
    db = get_db()
    db.execute(
        """
        INSERT INTO site_settings (id, homepage_alert, contact_line, contact_phone, updated_at)
        VALUES (
            1,
            ?,
            ?,
            ?,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            homepage_alert = excluded.homepage_alert,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            message or None,
            current_app.config.get("CAFE_CONTACT_LINE"),
            current_app.config.get("CAFE_CONTACT_PHONE"),
        ),
    )
    db.commit()


def update_site_contact(contact_line, contact_phone):
    db = get_db()
    db.execute(
        """
        INSERT INTO site_settings (id, homepage_alert, contact_line, contact_phone, updated_at)
        VALUES (
            1,
            ?,
            ?,
            ?,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            contact_line = excluded.contact_line,
            contact_phone = excluded.contact_phone,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            get_homepage_alert(),
            contact_line or None,
            contact_phone or None,
        ),
    )
    db.commit()


def update_homepage_image(image_path, alt_text):
    db = get_db()
    settings = get_site_settings()
    db.execute(
        """
        INSERT INTO site_settings (
            id,
            homepage_alert,
            homepage_image_path,
            homepage_image_alt,
            contact_line,
            contact_phone,
            updated_at
        )
        VALUES (
            1,
            ?,
            ?,
            ?,
            ?,
            ?,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            homepage_image_path = excluded.homepage_image_path,
            homepage_image_alt = excluded.homepage_image_alt,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            settings["homepage_alert"],
            image_path,
            alt_text or None,
            settings["contact_line"],
            settings["contact_phone"],
        ),
    )
    db.commit()


def get_homepage_images():
    db = get_db()
    images = db.execute(
        """
        SELECT id, image_path, alt_text, sort_order
        FROM homepage_images
        ORDER BY sort_order, id
        """
    ).fetchall()
    if images:
        return [dict(image) for image in images]
    return [
        {
            "id": None,
            "image_path": image_path,
            "alt_text": alt_text,
            "sort_order": sort_order,
        }
        for image_path, alt_text, sort_order in SEED_HOMEPAGE_IMAGES
    ]


def add_homepage_image(image_path, alt_text):
    db = get_db()
    next_sort_order = db.execute(
        """
        SELECT COALESCE(MAX(sort_order), 0) + 1
        FROM homepage_images
        """
    ).fetchone()[0]
    db.execute(
        """
        INSERT INTO homepage_images (image_path, alt_text, sort_order)
        VALUES (?, ?, ?)
        """,
        (image_path, alt_text, next_sort_order),
    )
    db.execute(
        """
        UPDATE site_settings
        SET homepage_image_path = NULL, homepage_image_alt = NULL
        WHERE id = 1
        """
    )
    db.commit()


def update_homepage_image_order(image_sort_orders):
    db = get_db()
    existing_images = db.execute(
        """
        SELECT id
        FROM homepage_images
        """
    ).fetchall()
    existing_image_ids = {row["id"] for row in existing_images}

    normalized_pairs = []
    for image_id, sort_order in image_sort_orders.items():
        if image_id not in existing_image_ids:
            continue
        normalized_pairs.append((image_id, max(1, int(sort_order))))

    normalized_pairs.sort(key=lambda pair: (pair[1], pair[0]))

    for index, (image_id, _sort_order) in enumerate(normalized_pairs, start=1):
        db.execute(
            """
            UPDATE homepage_images
            SET sort_order = ?
            WHERE id = ?
            """,
            (index, image_id),
        )
    db.commit()


def delete_homepage_image(image_id):
    db = get_db()
    image = db.execute(
        """
        SELECT id, image_path
        FROM homepage_images
        WHERE id = ?
        """,
        (image_id,),
    ).fetchone()
    if image is None:
        raise ValueError("Homepage image not found.")

    db.execute(
        "DELETE FROM homepage_images WHERE id = ?",
        (image_id,),
    )

    remaining_images = db.execute(
        """
        SELECT id
        FROM homepage_images
        ORDER BY sort_order, id
        """
    ).fetchall()

    for index, row in enumerate(remaining_images, start=1):
        db.execute(
            """
            UPDATE homepage_images
            SET sort_order = ?
            WHERE id = ?
            """,
            (index, row["id"]),
        )
    db.commit()
    return dict(image)


def clear_homepage_images():
    db = get_db()
    images = db.execute(
        """
        SELECT image_path
        FROM homepage_images
        """
    ).fetchall()
    db.execute("DELETE FROM homepage_images")
    db.commit()
    return [row["image_path"] for row in images]


def get_product_with_images(product_id):
    db = get_db()
    product = db.execute(
        """
        SELECT
            p.id,
            p.name,
            p.price_eur,
            p.description,
            sp.name AS stock_pool_name,
            sp.servings_available,
            sp.grams_per_serving
        FROM products p
        JOIN stock_pools sp ON sp.id = p.stock_pool_id
        WHERE p.id = ?
        """,
        (product_id,),
    ).fetchone()

    if product is None:
        return None

    images = db.execute(
        """
        SELECT id, image_path, alt_text, sort_order
        FROM product_images
        WHERE product_id = ?
        ORDER BY sort_order, id
        """,
        (product_id,),
    ).fetchall()

    return {"product": product, "images": images}


def add_product_image(product_id, image_path, alt_text):
    db = get_db()
    product = db.execute(
        "SELECT id FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    if product is None:
        raise ValueError("Choose a valid drink.")

    next_sort_order = db.execute(
        """
        SELECT COALESCE(MAX(sort_order), 0) + 1
        FROM product_images
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()[0]

    db.execute(
        """
        INSERT INTO product_images (product_id, image_path, alt_text, sort_order)
        VALUES (?, ?, ?, ?)
        """,
        (product_id, image_path, alt_text, next_sort_order),
    )
    db.commit()


def update_product_image_order(product_id, image_sort_orders):
    db = get_db()
    existing_images = db.execute(
        """
        SELECT id
        FROM product_images
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchall()
    existing_image_ids = {row["id"] for row in existing_images}

    normalized_pairs = []
    for image_id, sort_order in image_sort_orders.items():
        if image_id not in existing_image_ids:
            continue
        normalized_pairs.append((image_id, max(1, int(sort_order))))

    normalized_pairs.sort(key=lambda pair: (pair[1], pair[0]))

    for index, (image_id, _sort_order) in enumerate(normalized_pairs, start=1):
        db.execute(
            """
            UPDATE product_images
            SET sort_order = ?
            WHERE id = ? AND product_id = ?
            """,
            (index, image_id, product_id),
        )
    db.commit()


def delete_product_image(image_id):
    db = get_db()
    image = db.execute(
        """
        SELECT id, product_id, image_path
        FROM product_images
        WHERE id = ?
        """,
        (image_id,),
    ).fetchone()
    if image is None:
        raise ValueError("Image not found.")

    db.execute(
        "DELETE FROM product_images WHERE id = ?",
        (image_id,),
    )

    remaining_images = db.execute(
        """
        SELECT id
        FROM product_images
        WHERE product_id = ?
        ORDER BY sort_order, id
        """,
        (image["product_id"],),
    ).fetchall()

    for index, row in enumerate(remaining_images, start=1):
        db.execute(
            """
            UPDATE product_images
            SET sort_order = ?
            WHERE id = ?
            """,
            (index, row["id"]),
        )
    db.commit()
    return dict(image)


def create_product(name, price_eur, description, stock_pool_id):
    db = get_db()
    stock_pool = db.execute(
        "SELECT id FROM stock_pools WHERE id = ?",
        (stock_pool_id,),
    ).fetchone()
    if stock_pool is None:
        raise ValueError("Choose a valid stock pool.")

    cursor = db.execute(
        """
        INSERT INTO products (name, price_eur, description, stock_pool_id)
        VALUES (?, ?, ?, ?)
        """,
        (name, price_eur, description, stock_pool_id),
    )
    db.commit()
    return cursor.lastrowid


def update_product(product_id, name, price_eur, description, stock_pool_id):
    db = get_db()
    stock_pool = db.execute(
        "SELECT id FROM stock_pools WHERE id = ?",
        (stock_pool_id,),
    ).fetchone()
    if stock_pool is None:
        raise ValueError("Choose a valid stock pool.")

    cursor = db.execute(
        """
        UPDATE products
        SET name = ?, price_eur = ?, description = ?, stock_pool_id = ?
        WHERE id = ?
        """,
        (name, price_eur, description, stock_pool_id, product_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("Drink not found.")
    db.commit()


def delete_product(product_id):
    db = get_db()
    product = db.execute(
        """
        SELECT id
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    ).fetchone()
    if product is None:
        raise ValueError("Drink not found.")

    order_item_count = db.execute(
        """
        SELECT COUNT(*)
        FROM order_items
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()[0]
    if order_item_count:
        raise ValueError("Cannot delete a drink that already appears in orders.")

    images = db.execute(
        """
        SELECT image_path
        FROM product_images
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchall()

    db.execute(
        "DELETE FROM product_images WHERE product_id = ?",
        (product_id,),
    )
    db.execute(
        "DELETE FROM products WHERE id = ?",
        (product_id,),
    )
    db.commit()
    return [row["image_path"] for row in images]


def update_stock_pool(stock_pool_id, servings_available, grams_per_serving):
    db = get_db()
    cursor = db.execute(
        """
        UPDATE stock_pools
        SET servings_available = ?, grams_per_serving = ?
        WHERE id = ?
        """,
        (servings_available, grams_per_serving, stock_pool_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("Stock pool not found.")
    db.commit()


def get_admin_user_by_username(username):
    db = get_db()
    return db.execute(
        """
        SELECT id, username, password_hash, created_at, updated_at
        FROM admin_users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()


def refresh_admin_user_password_hash(admin_user_id, password):
    db = get_db()
    db.execute(
        """
        UPDATE admin_users
        SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (hash_admin_password(password), admin_user_id),
    )
    db.commit()


def _load_products_for_items(db, items):
    products = {}
    for product_id in items:
        product = db.execute(
            """
            SELECT
                p.id,
                p.name,
                p.price_eur,
                p.stock_pool_id,
                sp.name AS stock_pool_name,
                sp.servings_available
            FROM products p
            JOIN stock_pools sp ON sp.id = p.stock_pool_id
            WHERE p.id = ?
            """,
            (product_id,),
        ).fetchone()
        if product is not None:
            products[product_id] = product
    return products


def create_order(name, customer_contact, pickup_at, payment_method, notes, items):
    db = get_db()
    cancel_token = secrets.token_urlsafe(32)
    cancel_token_hash = generate_password_hash(cancel_token)
    phone_last4 = extract_contact_suffix(customer_contact)
    selected_items = []
    total_amount = 0.0
    requested_per_stock_pool = {}
    products = _load_products_for_items(db, items)

    if not customer_contact.strip():
        raise ValueError("Enter your WhatsApp number or Telegram handle.")

    try:
        datetime.strptime(pickup_at, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("Choose a valid pickup time.") from exc

    try:
        db.execute("BEGIN IMMEDIATE")

        for product_id, item_data in items.items():
            quantity = item_data["quantity"]
            preparation_style = item_data["preparation_style"]
            extra_syrup_g = float(item_data.get("extra_syrup_g", 0))
            milk_adjustment_ml = int(item_data.get("milk_adjustment_ml", 0))
            product = products.get(product_id)
            if product is None or quantity <= 0:
                continue
            if preparation_style not in PREPARATION_STYLES:
                raise ValueError("Choose a valid drink style.")
            if extra_syrup_g < MIN_SYRUP_ADJUSTMENT_G or extra_syrup_g > MAX_EXTRA_SYRUP_G:
                raise ValueError("Choose a valid syrup amount.")
            if (
                milk_adjustment_ml < MIN_MILK_ADJUSTMENT_ML
                or milk_adjustment_ml > MAX_MILK_ADJUSTMENT_ML
            ):
                raise ValueError("Choose a valid milk amount.")

            line_total = product["price_eur"] * quantity
            total_amount += line_total
            selected_items.append(
                {
                    "product_id": product["id"],
                    "name": product["name"],
                    "quantity": quantity,
                    "preparation_style": preparation_style,
                    "extra_syrup_g": extra_syrup_g,
                    "milk_adjustment_ml": milk_adjustment_ml,
                    "unit_price": product["price_eur"],
                    "stock_pool_id": product["stock_pool_id"],
                    "stock_pool_name": product["stock_pool_name"],
                }
            )
            requested_per_stock_pool[product["stock_pool_id"]] = (
                requested_per_stock_pool.get(product["stock_pool_id"], 0) + quantity
            )

        if not selected_items:
            raise ValueError("At least one item must be selected.")

        for stock_pool_id, requested_quantity in requested_per_stock_pool.items():
            stock_pool = db.execute(
                """
                SELECT id, name, servings_available
                FROM stock_pools
                WHERE id = ?
                """,
                (stock_pool_id,),
            ).fetchone()
            if stock_pool["servings_available"] < requested_quantity:
                raise InventoryError(
                    f"Not enough {stock_pool['name']} stock left. Remaining servings: "
                    f"{stock_pool['servings_available']}."
                )

        cursor = db.execute(
            """
            INSERT INTO orders (
                customer_name,
                customer_contact,
                phone_last4,
                pickup_at,
                payment_method,
                notes,
                total_amount,
                status,
                cancel_token_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                customer_contact.strip(),
                phone_last4,
                pickup_at,
                payment_method,
                notes,
                total_amount,
                "new",
                cancel_token_hash,
            ),
        )
        order_id = cursor.lastrowid

        db.executemany(
            """
            INSERT INTO order_items (
                order_id,
                product_id,
                quantity,
                preparation_style,
                syrup_level,
                milk_volume,
                extra_syrup_g,
                milk_adjustment_ml,
                unit_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order_id,
                    item["product_id"],
                    item["quantity"],
                    item["preparation_style"],
                    "custom" if item["extra_syrup_g"] else "standard",
                    "custom" if item["milk_adjustment_ml"] else "standard",
                    item["extra_syrup_g"],
                    item["milk_adjustment_ml"],
                    item["unit_price"],
                )
                for item in selected_items
            ],
        )

        for stock_pool_id, requested_quantity in requested_per_stock_pool.items():
            db.execute(
                """
                UPDATE stock_pools
                SET servings_available = servings_available - ?
                WHERE id = ?
                """,
                (requested_quantity, stock_pool_id),
            )
    except Exception:
        db.rollback()
        raise

    db.commit()
    return {"order_id": order_id, "cancel_token": cancel_token}


def get_order(order_id):
    db = get_db()
    order = db.execute(
        """
        SELECT
            id,
            customer_name,
            customer_contact,
            phone_last4,
            pickup_at,
            payment_method,
            notes,
            total_amount,
            status,
            cancel_token_hash,
            created_at
        FROM orders
        WHERE id = ?
        """,
        (order_id,),
    ).fetchone()

    if order is None:
        return None

    items = db.execute(
        """
        SELECT
            p.name,
            oi.quantity,
            oi.preparation_style,
            oi.syrup_level,
            oi.milk_volume,
            oi.extra_syrup_g,
            oi.milk_adjustment_ml,
            oi.unit_price
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
        """,
        (order_id,),
    ).fetchall()

    return {"order": order, "items": items}


def list_orders():
    db = get_db()
    orders = db.execute(
        """
        SELECT
            id,
            customer_name,
            customer_contact,
            phone_last4,
            pickup_at,
            payment_method,
            total_amount,
            status,
            cancel_token_hash,
            created_at
        FROM orders
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()

    grouped = []
    for order in orders:
        items = db.execute(
            """
            SELECT
                p.name,
                oi.quantity,
                oi.preparation_style,
                oi.syrup_level,
                oi.milk_volume,
                oi.extra_syrup_g,
                oi.milk_adjustment_ml,
                oi.unit_price
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY oi.id
            """,
            (order["id"],),
        ).fetchall()
        grouped.append({"order": order, "items": items})
    return grouped


def get_order_for_management(order_id, cancel_token):
    order_bundle = get_order(order_id)
    if order_bundle is None:
        return None

    token_hash = order_bundle["order"]["cancel_token_hash"]
    if not token_hash or not check_password_hash(token_hash, cancel_token):
        return None

    return order_bundle


def can_cancel_order(order, now=None):
    if now is None:
        now = datetime.now()
    if order["status"] != "new":
        return False
    try:
        pickup_at = datetime.strptime(order["pickup_at"], "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return False
    return now < pickup_at


def update_order_status(order_id, status):
    if status not in {"new", "paid", "collected"}:
        raise ValueError("Choose a valid order status.")

    db = get_db()
    cursor = db.execute(
        """
        UPDATE orders
        SET status = ?
        WHERE id = ? AND status != 'cancelled'
        """,
        (status, order_id),
    )
    if cursor.rowcount == 0:
        raise ValueError("Order not found or already cancelled.")
    db.commit()


def _restore_stock_and_cancel_order(db, order_id):
    items = db.execute(
        """
        SELECT oi.quantity, p.stock_pool_id
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    ).fetchall()

    restored_by_stock_pool = {}
    for item in items:
        restored_by_stock_pool[item["stock_pool_id"]] = (
            restored_by_stock_pool.get(item["stock_pool_id"], 0)
            + item["quantity"]
        )

    for stock_pool_id, quantity in restored_by_stock_pool.items():
        db.execute(
            """
            UPDATE stock_pools
            SET servings_available = servings_available + ?
            WHERE id = ?
            """,
            (quantity, stock_pool_id),
        )

    db.execute(
        """
        UPDATE orders
        SET status = 'cancelled'
        WHERE id = ?
        """,
        (order_id,),
    )


def cancel_order(order_id, cancel_token, now=None):
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute(
            """
            SELECT id, status, pickup_at, cancel_token_hash
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            db.rollback()
            return "not_found"
        if not order["cancel_token_hash"] or not check_password_hash(
            order["cancel_token_hash"],
            cancel_token,
        ):
            db.rollback()
            return "not_found"
        if not can_cancel_order(order, now=now):
            db.rollback()
            return "not_allowed"

        _restore_stock_and_cancel_order(db, order_id)
    except Exception:
        db.rollback()
        raise

    db.commit()
    return "cancelled"


def cancel_order_by_admin(order_id):
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute(
            """
            SELECT id, status
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            db.rollback()
            return "not_found"
        if order["status"] != "new":
            db.rollback()
            return "not_allowed"

        _restore_stock_and_cancel_order(db, order_id)
    except Exception:
        db.rollback()
        raise

    db.commit()
    return "cancelled"


def delete_order_record(order_id, now=None):
    if now is None:
        now = datetime.now()

    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute(
            """
            SELECT id, status, pickup_at
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            db.rollback()
            return "not_found"

        is_cancelled = order["status"] == "cancelled"
        is_past_pickup = False
        try:
            pickup_at = datetime.strptime(order["pickup_at"], "%Y-%m-%dT%H:%M")
            is_past_pickup = pickup_at < now
        except (TypeError, ValueError):
            pass

        if not is_cancelled and not is_past_pickup:
            db.rollback()
            return "not_allowed"

        db.execute(
            """
            DELETE FROM order_items
            WHERE order_id = ?
            """,
            (order_id,),
        )
        db.execute(
            """
            DELETE FROM orders
            WHERE id = ?
            """,
            (order_id,),
        )
    except Exception:
        db.rollback()
        raise

    db.commit()
    return "deleted"


def list_stock_pools():
    db = get_db()
    return db.execute(
        """
        SELECT id, name, servings_available, grams_per_serving
        FROM stock_pools
        ORDER BY id
        """
    ).fetchall()


@click.command("init-db")
def init_db_command():
    init_db()
    sync_admin_user_from_config()
    click.echo("Initialized the database.")


@click.command("reset-db")
def reset_db_command():
    reset_db()
    sync_admin_user_from_config()
    click.echo("Reset the database.")


@click.command("hash-password")
@click.argument("password")
def hash_password_command(password):
    click.echo(hash_admin_password(password))


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(reset_db_command)
    app.cli.add_command(hash_password_command)
