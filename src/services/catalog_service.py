from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Category, Product, ProductFormat, StockItem, UploadMode, Variant


# ────────────────── Categories ──────────────────
async def list_categories(session: AsyncSession, only_active: bool = True) -> Sequence[Category]:
    stmt = select(Category).order_by(Category.sort_order, Category.id)
    if only_active:
        stmt = stmt.where(Category.is_active.is_(True))
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    res = await session.execute(select(Category).where(Category.id == category_id))
    return res.scalar_one_or_none()


async def create_category(session: AsyncSession, name: str) -> Category:
    cat = Category(name=name, sort_order=0, is_active=True)
    session.add(cat)
    await session.flush()
    return cat


async def update_category(
    session: AsyncSession,
    category_id: int,
    *,
    name: str | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
) -> Category:
    cat = await get_category(session, category_id)
    if cat is None:
        raise ValueError("Категория не найдена")
    if name is not None:
        cat.name = name
    if is_active is not None:
        cat.is_active = is_active
    if sort_order is not None:
        cat.sort_order = sort_order
    await session.flush()
    return cat


async def delete_category(session: AsyncSession, category_id: int) -> None:
    cat = await get_category(session, category_id)
    if cat is None:
        return
    await session.delete(cat)
    await session.flush()


# ────────────────── Products ──────────────────
async def list_products(
    session: AsyncSession, category_id: int, only_active: bool = True
) -> Sequence[Product]:
    stmt = (
        select(Product)
        .where(Product.category_id == category_id)
        .order_by(Product.sort_order, Product.id)
    )
    if only_active:
        stmt = stmt.where(Product.is_active.is_(True))
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    res = await session.execute(select(Product).where(Product.id == product_id))
    return res.scalar_one_or_none()


async def create_product(
    session: AsyncSession,
    *,
    category_id: int,
    name: str,
    description: str | None = None,
    fmt: ProductFormat = ProductFormat.cookies_json,
    upload_mode: UploadMode = UploadMode.zip_files,
) -> Product:
    p = Product(
        category_id=category_id,
        name=name,
        description=description,
        format=fmt,
        upload_mode=upload_mode,
        sort_order=0,
        is_active=True,
    )
    session.add(p)
    await session.flush()
    return p


_UNSET = object()


async def update_product(
    session: AsyncSession,
    product_id: int,
    *,
    name: str | None = None,
    description: object = _UNSET,
    image_file_id: object = _UNSET,
    fmt: ProductFormat | None = None,
    upload_mode: UploadMode | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
) -> Product:
    p = await get_product(session, product_id)
    if p is None:
        raise ValueError("Товар не найден")
    if name is not None:
        p.name = name
    if description is not _UNSET:
        p.description = description  # None очистит описание
    if image_file_id is not _UNSET:
        p.image_file_id = image_file_id  # None очистит картинку
    if fmt is not None:
        p.format = fmt
    if upload_mode is not None:
        p.upload_mode = upload_mode
    if is_active is not None:
        p.is_active = is_active
    if sort_order is not None:
        p.sort_order = sort_order
    await session.flush()
    return p


async def delete_product(session: AsyncSession, product_id: int) -> None:
    p = await get_product(session, product_id)
    if p is None:
        return
    await session.delete(p)
    await session.flush()


# ────────────────── Variants ──────────────────
async def list_variants(
    session: AsyncSession, product_id: int, only_active: bool = True
) -> Sequence[Variant]:
    stmt = (
        select(Variant)
        .where(Variant.product_id == product_id)
        .order_by(Variant.sort_order, Variant.id)
    )
    if only_active:
        stmt = stmt.where(Variant.is_active.is_(True))
    res = await session.execute(stmt)
    return res.scalars().all()


async def get_variant(session: AsyncSession, variant_id: int) -> Variant | None:
    res = await session.execute(select(Variant).where(Variant.id == variant_id))
    return res.scalar_one_or_none()


async def create_variant(
    session: AsyncSession,
    *,
    product_id: int,
    name: str,
    price_rub: Decimal,
) -> Variant:
    v = Variant(
        product_id=product_id,
        name=name,
        price_rub=price_rub,
        sort_order=0,
        is_active=True,
    )
    session.add(v)
    await session.flush()
    return v


async def update_variant(
    session: AsyncSession,
    variant_id: int,
    *,
    name: str | None = None,
    price_rub: Decimal | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
) -> Variant:
    v = await get_variant(session, variant_id)
    if v is None:
        raise ValueError("Вариант не найден")
    if name is not None:
        v.name = name
    if price_rub is not None:
        v.price_rub = price_rub
    if is_active is not None:
        v.is_active = is_active
    if sort_order is not None:
        v.sort_order = sort_order
    await session.flush()
    return v


async def delete_variant(session: AsyncSession, variant_id: int) -> None:
    v = await get_variant(session, variant_id)
    if v is None:
        return
    await session.delete(v)
    await session.flush()


# ────────────────── Stock counts ──────────────────
async def stock_count(session: AsyncSession, variant_id: int) -> int:
    res = await session.execute(
        select(func.count(StockItem.id)).where(
            StockItem.variant_id == variant_id, StockItem.is_sold.is_(False)
        )
    )
    return int(res.scalar() or 0)


async def stock_counts_for_variants(
    session: AsyncSession, variant_ids: Sequence[int]
) -> dict[int, int]:
    if not variant_ids:
        return {}
    res = await session.execute(
        select(StockItem.variant_id, func.count(StockItem.id))
        .where(StockItem.variant_id.in_(variant_ids), StockItem.is_sold.is_(False))
        .group_by(StockItem.variant_id)
    )
    counts = {vid: 0 for vid in variant_ids}
    for vid, c in res.all():
        counts[vid] = int(c)
    return counts
