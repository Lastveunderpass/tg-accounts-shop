from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import StockBatch, StockItem, Variant
from src.utils.parsers import ParsedItem


async def add_stock_items(
    session: AsyncSession,
    *,
    variant_id: int,
    admin_id: int,
    items: Sequence[ParsedItem],
    note: str | None = None,
) -> StockBatch:
    """Создаёт партию + StockItem'ы. Возвращает батч."""
    variant = await session.get(Variant, variant_id)
    if variant is None:
        raise ValueError("Вариант не найден")

    batch = StockBatch(
        variant_id=variant_id,
        admin_id=admin_id,
        items_count=len(items),
        note=note,
    )
    session.add(batch)
    await session.flush()

    for item in items:
        si = StockItem(
            variant_id=variant_id,
            batch_id=batch.id,
            payload=item.payload,
            file_name=item.file_name,
            is_sold=False,
        )
        session.add(si)
    await session.flush()
    return batch


async def list_unsold(session: AsyncSession, variant_id: int, limit: int = 100) -> Sequence[StockItem]:
    res = await session.execute(
        select(StockItem)
        .where(StockItem.variant_id == variant_id, StockItem.is_sold.is_(False))
        .order_by(StockItem.id)
        .limit(limit)
    )
    return res.scalars().all()


async def reserve_unsold(
    session: AsyncSession, variant_id: int, qty: int
) -> list[StockItem]:
    """Атомарно помечает qty штук как is_sold=True. Возвращает список зарезервированных.
    Если в наличии меньше qty — поднимает ValueError, ничего не меняя."""
    res = await session.execute(
        select(StockItem)
        .where(StockItem.variant_id == variant_id, StockItem.is_sold.is_(False))
        .order_by(StockItem.id)
        .limit(qty)
        .with_for_update(skip_locked=False)
    )
    items = list(res.scalars().all())
    if len(items) < qty:
        raise ValueError(f"Недостаточно товара: запрошено {qty}, в наличии {len(items)}")
    for it in items:
        it.is_sold = True
    await session.flush()
    return items


async def release_stock_items(session: AsyncSession, items: Sequence[StockItem]) -> None:
    """Возвращает товар в сток (для возврата покупки)."""
    for it in items:
        it.is_sold = False
        it.sold_to_user_id = None
        it.sold_at = None
        it.order_item_id = None
    await session.flush()


async def delete_batch(session: AsyncSession, batch_id: int) -> int:
    """Удаляет батч и все его непроданные StockItem'ы. Возвращает количество удалённых."""
    res = await session.execute(
        select(StockItem).where(StockItem.batch_id == batch_id, StockItem.is_sold.is_(False))
    )
    items = list(res.scalars().all())
    for it in items:
        await session.delete(it)
    batch = await session.get(StockBatch, batch_id)
    if batch is not None:
        await session.delete(batch)
    await session.flush()
    return len(items)


async def list_batches(
    session: AsyncSession, variant_id: int, limit: int = 50
) -> Sequence[StockBatch]:
    res = await session.execute(
        select(StockBatch)
        .where(StockBatch.variant_id == variant_id)
        .order_by(StockBatch.id.desc())
        .limit(limit)
    )
    return res.scalars().all()
