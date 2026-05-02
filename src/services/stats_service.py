from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Category,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    Topup,
    TopupStatus,
    User,
    Variant,
)


async def revenue_total(session: AsyncSession) -> Decimal:
    res = await session.execute(
        select(func.coalesce(func.sum(Order.total_rub), 0)).where(Order.status == OrderStatus.paid)
    )
    return Decimal(res.scalar() or 0)


async def revenue_for_period(session: AsyncSession, since: datetime) -> Decimal:
    res = await session.execute(
        select(func.coalesce(func.sum(Order.total_rub), 0)).where(
            Order.status == OrderStatus.paid, Order.created_at >= since
        )
    )
    return Decimal(res.scalar() or 0)


async def topups_total(session: AsyncSession) -> Decimal:
    res = await session.execute(
        select(func.coalesce(func.sum(Topup.amount_rub), 0)).where(Topup.status == TopupStatus.paid)
    )
    return Decimal(res.scalar() or 0)


async def topups_for_period(session: AsyncSession, since: datetime) -> Decimal:
    res = await session.execute(
        select(func.coalesce(func.sum(Topup.amount_rub), 0)).where(
            Topup.status == TopupStatus.paid, Topup.created_at >= since
        )
    )
    return Decimal(res.scalar() or 0)


async def users_count(session: AsyncSession) -> int:
    res = await session.execute(select(func.count(User.id)))
    return int(res.scalar() or 0)


async def new_users_for_period(session: AsyncSession, since: datetime) -> int:
    res = await session.execute(
        select(func.count(User.id)).where(User.created_at >= since)
    )
    return int(res.scalar() or 0)


async def orders_count_for_period(session: AsyncSession, since: datetime) -> int:
    res = await session.execute(
        select(func.count(Order.id)).where(
            Order.status == OrderStatus.paid, Order.created_at >= since
        )
    )
    return int(res.scalar() or 0)


async def revenue_by_category(session: AsyncSession, since: datetime | None = None) -> list[tuple[str, Decimal, int]]:
    stmt = (
        select(
            Category.name,
            func.coalesce(func.sum(OrderItem.unit_price_rub), 0),
            func.count(OrderItem.id),
        )
        .join(Variant, Variant.id == OrderItem.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .join(Category, Category.id == Product.category_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == OrderStatus.paid)
        .group_by(Category.id)
        .order_by(func.sum(OrderItem.unit_price_rub).desc())
    )
    if since is not None:
        stmt = stmt.where(Order.created_at >= since)
    res = await session.execute(stmt)
    return [(name, Decimal(s or 0), int(c or 0)) for name, s, c in res.all()]


async def top_variants(
    session: AsyncSession, since: datetime | None = None, limit: int = 5
) -> list[tuple[str, str, int, Decimal]]:
    stmt = (
        select(
            Product.name,
            Variant.name,
            func.count(OrderItem.id),
            func.coalesce(func.sum(OrderItem.unit_price_rub), 0),
        )
        .join(Variant, Variant.id == OrderItem.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == OrderStatus.paid)
        .group_by(Variant.id)
        .order_by(func.count(OrderItem.id).desc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(Order.created_at >= since)
    res = await session.execute(stmt)
    return [(p, v, int(c), Decimal(s or 0)) for p, v, c, s in res.all()]


def utc_now() -> datetime:
    return datetime.now(UTC)


def since_days(days: int) -> datetime:
    return utc_now() - timedelta(days=days)
