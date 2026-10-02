from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import Product


def list_products(
    db: Session, *, query: str | None, category: str | None, page: int, page_size: int
) -> tuple[list[Product], int]:
    conditions = [Product.active.is_(True)]
    if query:
        term = f"%{query.strip()}%"
        conditions.append(or_(Product.name.ilike(term), Product.description.ilike(term)))
    if category:
        conditions.append(Product.category.has(slug=category))
    total = db.scalar(select(func.count(Product.id)).where(*conditions)) or 0
    products = db.scalars(
        select(Product)
        .where(*conditions)
        .options(selectinload(Product.variants), selectinload(Product.images))
        .order_by(Product.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(products), total


def list_products_admin(db: Session, *, page: int, page_size: int) -> tuple[list[Product], int]:
    """Every product regardless of active status, with every variant
    regardless of active status -- unlike list_products, which is scoped to
    what a shopper should see. Admin needs the full picture to reactivate a
    deactivated listing."""
    total = db.scalar(select(func.count(Product.id))) or 0
    products = db.scalars(
        select(Product)
        .options(selectinload(Product.variants), selectinload(Product.images))
        .order_by(Product.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(products), total
