CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS site_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    homepage_alert TEXT,
    contact_line TEXT,
    contact_phone TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    servings_available INTEGER NOT NULL,
    grams_per_serving INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price_eur REAL NOT NULL,
    description TEXT NOT NULL,
    stock_pool_id INTEGER NOT NULL,
    FOREIGN KEY (stock_pool_id) REFERENCES stock_pools (id)
);

CREATE TABLE IF NOT EXISTS product_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    alt_text TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products (id)
);

CREATE TABLE IF NOT EXISTS pickup_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pickup_date TEXT NOT NULL UNIQUE,
    is_available INTEGER NOT NULL DEFAULT 1,
    start_time TEXT NOT NULL DEFAULT '16:00',
    end_time TEXT NOT NULL DEFAULT '21:00',
    slot_capacity INTEGER NOT NULL DEFAULT 2,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    customer_contact TEXT NOT NULL,
    phone_last4 TEXT NOT NULL,
    pickup_at TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    notes TEXT,
    total_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    cancel_token_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    preparation_style TEXT NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (id),
    FOREIGN KEY (product_id) REFERENCES products (id)
);
