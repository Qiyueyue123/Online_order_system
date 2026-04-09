import sqlite3
from pathlib import Path
from datetime import datetime

import click
from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash


SEED_STOCK_POOLS = [
    ("Ikuyo", 25, 4),
    ("Sayaka", 5, 4),
]

SEED_MENU = [
    (
        "Ikuyo Matcha Latte",
        4.00,
        "Ippodo Ikuyo with low-fat milk.",
        "Ikuyo",
    ),
    (
        "Strawberry Ikuyo Matcha Latte",
        5.00,
        "Strawberry puree, low-fat milk, and Ippodo Ikuyo.",
        "Ikuyo",
    ),
    (
        "Sayaka Matcha Latte",
        5.00,
        "Ippodo Sayaka with low-fat milk.",
        "Sayaka",
    ),
]

SEED_PRODUCT_IMAGES = {
    "Ikuyo Matcha Latte": [
        (
            "/static/images/ikuyo-latte-1.svg",
            "Ikuyo matcha latte front view",
            1,
        ),
        (
            "/static/images/ikuyo-latte-2.svg",
            "Ikuyo matcha latte close-up foam view",
            2,
        ),
    ],
    "Strawberry Ikuyo Matcha Latte": [
        (
            "/static/images/strawberry-ikuyo-1.svg",
            "Strawberry Ikuyo matcha latte layered view",
            1,
        ),
        (
            "/static/images/strawberry-ikuyo-2.svg",
            "Strawberry Ikuyo matcha latte top garnish view",
            2,
        ),
    ],
    "Sayaka Matcha Latte": [
        (
            "/static/images/sayaka-latte-1.svg",
            "Sayaka matcha latte wide cup view",
            1,
        ),
        (
            "/static/images/sayaka-latte-2.svg",
            "Sayaka matcha latte whisk texture view",
            2,
        ),
    ],
}

PREPARATION_STYLES = {
    "type_1": "Type 1: whisk with water, add low-fat milk",
    "type_2": "Type 2: whisk with oat or regular milk for a frothier, thicker drink",
}


class InventoryError(ValueError):
    pass


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
    _seed_inventory(db)
    _seed_menu(db)
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
        if admin_user is None or not check_password_hash(admin_user["password_hash"], raw_password):
            resolved_password_hash = generate_password_hash(raw_password)
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


def _seed_inventory(db):
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


def get_homepage_alert():
    db = get_db()
    row = db.execute(
        """
        SELECT homepage_alert
        FROM site_settings
        WHERE id = 1
        """
    ).fetchone()
    if row is None:
        return None
    return row["homepage_alert"]


def update_homepage_alert(message):
    db = get_db()
    db.execute(
        """
        INSERT INTO site_settings (id, homepage_alert, updated_at)
        VALUES (1, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            homepage_alert = excluded.homepage_alert,
            updated_at = CURRENT_TIMESTAMP
        """,
        (message or None,),
    )
    db.commit()


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


def create_order(name, phone_last4, pickup_at, payment_method, notes, items):
    db = get_db()
    selected_items = []
    total_amount = 0.0
    requested_per_stock_pool = {}
    products = _load_products_for_items(db, items)

    if len(phone_last4) != 4 or not phone_last4.isdigit():
        raise ValueError("Enter the last 4 digits of your phone number.")

    try:
        datetime.strptime(pickup_at, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("Choose a valid pickup time.") from exc

    try:
        db.execute("BEGIN IMMEDIATE")

        for product_id, item_data in items.items():
            quantity = item_data["quantity"]
            preparation_style = item_data["preparation_style"]
            product = products.get(product_id)
            if product is None or quantity <= 0:
                continue
            if preparation_style not in PREPARATION_STYLES:
                raise ValueError("Choose a valid drink style.")

            line_total = product["price_eur"] * quantity
            total_amount += line_total
            selected_items.append(
                {
                    "product_id": product["id"],
                    "name": product["name"],
                    "quantity": quantity,
                    "preparation_style": preparation_style,
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
                phone_last4,
                pickup_at,
                payment_method,
                notes,
                total_amount,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, phone_last4, pickup_at, payment_method, notes, total_amount, "new"),
        )
        order_id = cursor.lastrowid

        db.executemany(
            """
            INSERT INTO order_items (
                order_id,
                product_id,
                quantity,
                preparation_style,
                unit_price
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    order_id,
                    item["product_id"],
                    item["quantity"],
                    item["preparation_style"],
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
    return order_id


def get_order(order_id):
    db = get_db()
    order = db.execute(
        """
        SELECT
            id,
            customer_name,
            phone_last4,
            pickup_at,
            payment_method,
            notes,
            total_amount,
            status,
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
            phone_last4,
            pickup_at,
            payment_method,
            total_amount,
            status,
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
    click.echo(generate_password_hash(password))


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(reset_db_command)
    app.cli.add_command(hash_password_command)
