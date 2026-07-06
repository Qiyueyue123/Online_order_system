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
