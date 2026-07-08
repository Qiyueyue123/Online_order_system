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


def _catalog(matcha: Category, tools: Category) -> list[tuple[str, Callable[[], Product]]]:
    """Catalog specs as (slug, factory) pairs.

    Factories defer construction: `Product(category=...)` eagerly attaches
    the new product to the session through the relationship cascade, so we
    only build the products whose slug is actually missing.
    """
    return [
        (
            "uji-ceremonial-matcha",
            lambda: Product(
                category=matcha,
                slug="uji-ceremonial-matcha",
                name="Uji Ceremonial Matcha",
                description="A fictional first-harvest matcha with sweet pea and cocoa notes.",
                variants=[
                    Variant(
                        sku="UJI-30",
                        name="30 g tin",
                        weight_grams=30,
                        price_sgd_cents=3800,
                        stock_on_hand=24,
                    ),
                    Variant(
                        sku="UJI-60",
                        name="60 g tin",
                        weight_grams=60,
                        price_sgd_cents=6900,
                        stock_on_hand=12,
                    ),
                ],
                images=[
                    ProductImage(
                        url="/legacy-assets/matcha-showcase.svg",
                        alt_text="Illustrated green matcha tin",
                    )
                ],
            ),
        ),
        (
            "asa-daily-matcha",
            lambda: Product(
                category=matcha,
                slug="asa-daily-matcha",
                name="Asa Daily Matcha",
                description=(
                    "A fictional everyday grade blended for lattes and baking — "
                    "grassy, round, and forgiving of hot milk."
                ),
                variants=[
                    Variant(
                        sku="ASA-80",
                        name="80 g pouch",
                        weight_grams=80,
                        price_sgd_cents=2400,
                        stock_on_hand=40,
                    ),
                    Variant(
                        sku="ASA-200",
                        name="200 g pouch",
                        weight_grams=200,
                        price_sgd_cents=4900,
                        stock_on_hand=22,
                    ),
                ],
            ),
        ),
        (
            "okumidori-single-cultivar",
            lambda: Product(
                category=matcha,
                slug="okumidori-single-cultivar",
                name="Okumidori Single Cultivar",
                description=(
                    "A fictional single-cultivar lot, shaded long for deep umami "
                    "and a quiet, lingering sweetness."
                ),
                variants=[
                    Variant(
                        sku="OKU-30",
                        name="30 g tin",
                        weight_grams=30,
                        price_sgd_cents=4600,
                        stock_on_hand=16,
                    ),
                ],
            ),
        ),
        (
            "first-bowl-sampler",
            lambda: Product(
                category=matcha,
                slug="first-bowl-sampler",
                name="First Bowl Sampler",
                description=(
                    "Three fictional 10 g tins — ceremonial, daily and single "
                    "cultivar — for finding the bowl you return to."
                ),
                variants=[
                    Variant(
                        sku="SAMPLER-3X10",
                        name="3 × 10 g tins",
                        weight_grams=30,
                        price_sgd_cents=3200,
                        stock_on_hand=20,
                    ),
                ],
            ),
        ),
        (
            "bamboo-whisk",
            lambda: Product(
                category=tools,
                slug="bamboo-whisk",
                name="Bamboo Whisk",
                description="Hand-finished 80-prong chasen for a fine, even foam.",
                variants=[
                    Variant(
                        sku="CHASEN-80",
                        name="80 prong",
                        weight_grams=45,
                        price_sgd_cents=2800,
                        stock_on_hand=18,
                    )
                ],
            ),
        ),
        (
            "kuro-chawan",
            lambda: Product(
                category=tools,
                slug="kuro-chawan",
                name="Kuro Chawan",
                description=(
                    "A fictional wide-lipped tea bowl in a deep iron glaze, "
                    "thrown to sit low and steady in the hands."
                ),
                variants=[
                    Variant(
                        sku="CHAWAN-KURO",
                        name="Iron glaze",
                        weight_grams=380,
                        price_sgd_cents=6200,
                        stock_on_hand=10,
                    ),
                    Variant(
                        sku="CHAWAN-SHIRO",
                        name="Ash white glaze",
                        weight_grams=360,
                        price_sgd_cents=6200,
                        stock_on_hand=8,
                    ),
                ],
            ),
        ),
        (
            "bamboo-chashaku",
            lambda: Product(
                category=tools,
                slug="bamboo-chashaku",
                name="Bamboo Chashaku",
                description=(
                    "A slender fictional scoop carved from a single node of "
                    "smoked bamboo — two scoops make one bowl."
                ),
                variants=[
                    Variant(
                        sku="CHASHAKU-STD",
                        name="Smoked bamboo",
                        weight_grams=8,
                        price_sgd_cents=1600,
                        stock_on_hand=26,
                    ),
                ],
            ),
        ),
        (
            "matcha-sifter",
            lambda: Product(
                category=tools,
                slug="matcha-sifter",
                name="Matcha Sifter",
                description=(
                    "A fine stainless furui that breaks clumps before whisking, "
                    "for a smoother bowl every time."
                ),
                variants=[
                    Variant(
                        sku="FURUI-STD",
                        name="Fine mesh",
                        weight_grams=90,
                        price_sgd_cents=2200,
                        stock_on_hand=14,
                    ),
                ],
            ),
        ),
    ]


def seed() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _bootstrap_admin(db)
        matcha = _get_or_create_category(db, "matcha", "Matcha tins")
        tools = _get_or_create_category(db, "tools", "Tea tools")
        existing = set(db.scalars(select(Product.slug)))
        for slug, build in _catalog(matcha, tools):
            if slug not in existing:
                db.add(build())
        db.commit()


if __name__ == "__main__":
    seed()
