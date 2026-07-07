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


def seed() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _bootstrap_admin(db)
        if db.scalar(select(Product.id).limit(1)):
            return
        ceremonial = Category(slug="matcha", name="Matcha tins")
        tools = Category(slug="tools", name="Tea tools")
        db.add_all([ceremonial, tools])
        products = [
            Product(
                category=ceremonial,
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
            Product(
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
        ]
        db.add_all(products)
        db.commit()


if __name__ == "__main__":
    seed()
