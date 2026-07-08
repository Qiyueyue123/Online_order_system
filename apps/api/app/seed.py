from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine
from .models import Category, Product, ProductImage, Role, User, Variant
from .security import hash_password


def _bootstrap_admin(db: Session) -> None:
    """Create-or-promote the admin account from ADMIN_EMAIL / ADMIN_PASSWORD.

    There is no admin signup flow in the API (by design: admin accounts are
    provisioned out-of-band, not self-served). This is the only bootstrap path
    today. It's a no-op unless both env vars are set, and idempotent when they
    are: re-running just refreshes the password/role on the existing row
    instead of creating duplicates, so it's safe to run on every deploy.
    """
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    email = settings.admin_email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        db.add(
            User(
                email=email,
                name="Administrator",
                password_hash=hash_password(settings.admin_password),
                role=Role.ADMIN,
                email_verified=True,
            )
        )
    else:
        user.role = Role.ADMIN
        user.password_hash = hash_password(settings.admin_password)
    db.commit()


def _get_or_create_category(db: Session, slug: str, name: str) -> Category:
    category = db.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        category = Category(slug=slug, name=name)
        db.add(category)
    return category


def _catalog(drinks: Category, matcha: Category) -> list[tuple[str, Callable[[], Product]]]:
    """Catalog specs as (slug, factory) pairs.

    Factories defer construction: `Product(category=...)` eagerly attaches
    the new product to the session through the relationship cascade, so we
    only build the products whose slug is actually missing.
    """
    return [
        (
            "sayaka-latte",
            lambda: Product(
                category=drinks,
                slug="sayaka-latte",
                name="Sayaka Latte",
                description=(
                    "Our everyday matcha latte, whisked to order with oat or whole "
                    "milk. Balanced and gently sweet — the one to start with."
                ),
                variants=[
                    Variant(
                        sku="SAYAKA-ICED",
                        name="Iced",
                        weight_grams=350,
                        price_cents=4900,
                        stock_on_hand=25,
                    ),
                    Variant(
                        sku="SAYAKA-HOT",
                        name="Hot",
                        weight_grams=300,
                        price_cents=4900,
                        stock_on_hand=25,
                    ),
                ],
                images=[
                    ProductImage(
                        url="/media/sayaka-latte-real-1.webp",
                        alt_text="Sayaka matcha latte",
                    ),
                    ProductImage(
                        url="/media/sayaka-latte-real-2.png",
                        alt_text="Sayaka latte top view",
                    ),
                ],
            ),
        ),
        (
            "ikuyo-latte",
            lambda: Product(
                category=drinks,
                slug="ikuyo-latte",
                name="Ikuyo Latte",
                description=(
                    "Our signature: a double shot of ceremonial-grade matcha "
                    "whisked into milk over ice or steamed hot. Bolder, greener, "
                    "for the days that need it."
                ),
                variants=[
                    Variant(
                        sku="IKUYO-ICED",
                        name="Iced",
                        weight_grams=350,
                        price_cents=5500,
                        stock_on_hand=20,
                    ),
                    Variant(
                        sku="IKUYO-HOT",
                        name="Hot",
                        weight_grams=300,
                        price_cents=5500,
                        stock_on_hand=20,
                    ),
                ],
                images=[
                    ProductImage(
                        url="/media/ikuyo-latte-real-1.webp",
                        alt_text="Ikuyo double-shot matcha latte",
                    ),
                    ProductImage(
                        url="/media/ikuyo-latte-real-2.png",
                        alt_text="Ikuyo latte close-up",
                    ),
                ],
            ),
        ),
        (
            "matcha-straight",
            lambda: Product(
                category=drinks,
                slug="matcha-straight",
                name="Usucha (Straight Matcha)",
                description=(
                    "No milk, no ice — just matcha whisked traditionally with hot "
                    "water into a thin, frothy bowl. Made fresh at pickup."
                ),
                variants=[
                    Variant(
                        sku="USUCHA-BOWL",
                        name="Bowl",
                        weight_grams=200,
                        price_cents=3900,
                        stock_on_hand=30,
                    ),
                ],
            ),
        ),
        (
            "uji-ceremonial-matcha",
            lambda: Product(
                category=matcha,
                slug="uji-ceremonial-matcha",
                name="Uji Ceremonial Matcha",
                description="A first-harvest matcha with sweet pea and cocoa notes.",
                variants=[
                    Variant(
                        sku="UJI-30",
                        name="30 g tin",
                        weight_grams=30,
                        price_cents=28900,
                        stock_on_hand=24,
                    ),
                    Variant(
                        sku="UJI-60",
                        name="60 g tin",
                        weight_grams=60,
                        price_cents=52900,
                        stock_on_hand=12,
                    ),
                ],
            ),
        ),
        (
            "bamboo-whisk",
            lambda: Product(
                category=matcha,
                slug="bamboo-whisk",
                name="Bamboo Whisk",
                description="Hand-finished 80-prong chasen for a fine, even foam.",
                variants=[
                    Variant(
                        sku="CHASEN-80",
                        name="80 prong",
                        weight_grams=45,
                        price_cents=21900,
                        stock_on_hand=18,
                    )
                ],
            ),
        ),
    ]


def seed() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _bootstrap_admin(db)
        drinks = _get_or_create_category(db, "drinks", "Drinks")
        matcha = _get_or_create_category(db, "matcha", "Matcha tins")
        existing = set(db.scalars(select(Product.slug)))
        for slug, build in _catalog(drinks, matcha):
            if slug not in existing:
                db.add(build())
        db.commit()


if __name__ == "__main__":
    seed()
