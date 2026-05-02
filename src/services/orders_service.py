from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Order,
    OrderItem,
    OrderStatus,
    PromoCode,
    PromoUsage,
    StockItem,
    User,
    Variant,
)
from src.services import promo_service, stock_service
from src.utils.money import quantize_rub


@dataclass
class PurchaseResult:
    order: Order
    items: list[StockItem]
    variant: Variant
    promo: PromoCode | None


class OrderError(Exception):
    pass


async def create_purchase(
    session: AsyncSession,
    *,
    user: User,
    variant: Variant,
    qty: int,
    promo_code: str | None = None,
    max_qty_per_order: int = 10,
) -> PurchaseResult:
    """Транзакционная покупка: резервирует сток, списывает с баланса, создаёт Order."""
    if user.is_banned:
        raise OrderError("Пользователь заблокирован")
    if qty < 1:
        raise OrderError("Количество должно быть ≥ 1")
    if qty > max_qty_per_order:
        raise OrderError(f"Максимум {max_qty_per_order} шт. за один заказ")
    if not variant.is_active:
        raise OrderError("Этот вариант временно недоступен")

    subtotal = quantize_rub(variant.price_rub * Decimal(qty))

    promo: PromoCode | None = None
    discount = Decimal("0")
    if promo_code:
        promo, discount = await promo_service.validate_promo_for_purchase(
            session,
            code=promo_code,
            user=user,
            variant=variant,
            subtotal_rub=subtotal,
            qty=qty,
        )

    total = quantize_rub(subtotal - discount)
    if total < 0:
        total = Decimal("0")

    if user.balance_rub < total:
        raise OrderError("Недостаточно средств на балансе")

    # резервируем сток
    stock_items = await stock_service.reserve_unsold(session, variant.id, qty)

    # списываем с баланса
    user.balance_rub = quantize_rub(user.balance_rub - total)
    user.total_spent_rub = quantize_rub((user.total_spent_rub or Decimal("0")) + total)

    # создаём Order и OrderItem'ы
    order = Order(
        user_id=user.id,
        status=OrderStatus.paid,
        subtotal_rub=subtotal,
        discount_rub=discount,
        total_rub=total,
        promo_code_id=promo.id if promo else None,
    )
    session.add(order)
    await session.flush()

    for stock_item in stock_items:
        oi = OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            stock_item_id=stock_item.id,
            unit_price_rub=variant.price_rub,
        )
        session.add(oi)
        await session.flush()
        stock_item.sold_to_user_id = user.id
        stock_item.sold_at = datetime.now(UTC)
        stock_item.order_item_id = oi.id

    if promo is not None:
        promo.used_count += 1
        session.add(PromoUsage(promo_id=promo.id, user_id=user.id, order_id=order.id))

    await session.flush()
    return PurchaseResult(order=order, items=list(stock_items), variant=variant, promo=promo)


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def list_user_orders(
    session: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> Sequence[Order]:
    res = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


async def order_items_with_stock(
    session: AsyncSession, order_id: int
) -> list[tuple[OrderItem, StockItem | None]]:
    res = await session.execute(
        select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
    )
    items = list(res.scalars().all())
    out: list[tuple[OrderItem, StockItem | None]] = []
    for oi in items:
        stock = await session.get(StockItem, oi.stock_item_id) if oi.stock_item_id else None
        out.append((oi, stock))
    return out


async def refund_order(
    session: AsyncSession,
    *,
    order_id: int,
    admin_id: int,
    return_money: bool,
    return_stock: bool,
    note: str | None = None,
) -> Order:
    order = await get_order(session, order_id)
    if order is None:
        raise OrderError("Заказ не найден")
    if order.status == OrderStatus.refunded:
        raise OrderError("Заказ уже возвращён")

    user = await session.get(User, order.user_id)
    if user is None:
        raise OrderError("Пользователь заказа не найден")

    items = await order_items_with_stock(session, order_id)

    if return_stock:
        stock_items = [si for _, si in items if si is not None]
        await stock_service.release_stock_items(session, stock_items)

    if return_money:
        user.balance_rub = quantize_rub((user.balance_rub or Decimal("0")) + order.total_rub)
        user.total_spent_rub = quantize_rub(
            max(Decimal("0"), (user.total_spent_rub or Decimal("0")) - order.total_rub)
        )

    order.status = OrderStatus.refunded
    order.refunded_at = datetime.now(UTC)
    order.refunded_by_admin_id = admin_id
    order.refund_note = note

    await session.flush()
    return order
