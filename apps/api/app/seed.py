from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine
from .models import Category, PickupDay, Product, ProductImage, Role, User, Variant
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
                    "Our everyday matcha latte, whisked from Niko Neko Ajisai 2.0 "
                    "to order with oat or whole milk. Balanced and gently sweet — "
                    "the one to start with."
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
                    "Our signature: a double shot of Niko Neko Ajisai 2.0 whisked "
                    "into milk over ice or steamed hot. Bolder, greener, for the "
                    "days that need it."
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
                    "No milk, no ice — just Niko Neko Ajisai 2.0 whisked "
                    "traditionally with hot water into a thin, frothy bowl. Made "
                    "fresh at pickup."
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
            "ajisai-matcha",
            lambda: Product(
                category=matcha,
                slug="ajisai-matcha",
                name="Niko Neko Ajisai 2.0",
                description=(
                    "The matcha our drinks are whisked from: a ceremonial-grade "
                    "single-cultivar Yabukita from Mie, with a nutty, creamy umami "
                    "profile and a gentle finish."
                ),
                variants=[
                    Variant(
                        sku="AJISAI-30",
                        name="30 g jar",
                        weight_grams=30,
                        price_cents=24900,
                        stock_on_hand=10,
                    ),
                    Variant(
                        sku="AJISAI-80",
                        name="80 g jar",
                        weight_grams=80,
                        price_cents=54900,
                        stock_on_hand=6,
                    ),
                ],
                images=[
                    ProductImage(
                        url="/media/ajisai-01.jpg",
                        alt_text="Niko Neko Ajisai 2.0 matcha jar",
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


def _seed_pickup_days(db: Session) -> None:
    """Pickup slots for the next 7 days, 16:00-19:00 in 15-minute steps, 2 per slot.

    Idempotent: only dates without a PickupDay row are created, so re-running the
    seed never clobbers availability/capacity tweaks made through the admin API.
    """
    today = datetime.now(UTC).date()
    wanted = [today + timedelta(days=offset) for offset in range(7)]
    existing = set(db.scalars(select(PickupDay.date).where(PickupDay.date.in_(wanted))))
    for day in wanted:
        if day not in existing:
            db.add(
                PickupDay(
                    date=day,
                    start_time=time(16, 0),
                    end_time=time(19, 0),
                    slot_minutes=15,
                    slot_capacity=2,
                )
            )


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
        _seed_pickup_days(db)
        db.commit()


if __name__ == "__main__":
    seed()
