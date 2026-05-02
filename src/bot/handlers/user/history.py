from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import texts
from src.db.models import Product, User, Variant
from src.services import orders_service
from src.utils.money import fmt_rub
from src.utils.parsers import build_zip_archive

router = Router(name="history")


@router.message(F.text == texts.MENU_HISTORY)
async def menu_history(message: Message, user: User, session: AsyncSession) -> None:
    orders = await orders_service.list_user_orders(session, user.id, limit=15)
    if not orders:
        await message.answer(texts.HISTORY_EMPTY)
        return
    rows: list[list[InlineKeyboardButton]] = []
    for o in orders:
        # суммарное количество и название первого товара (для подписи)
        items = await orders_service.order_items_with_stock(session, o.id)
        qty = len(items)
        first_variant = None
        if items:
            v_res = await session.execute(
                select(Variant).where(Variant.id == items[0][0].variant_id)
            )
            first_variant = v_res.scalar_one_or_none()
        prod_name = ""
        if first_variant is not None:
            p_res = await session.execute(
                select(Product).where(Product.id == first_variant.product_id)
            )
            prod = p_res.scalar_one_or_none()
            prod_name = prod.name if prod else ""
        label = (
            f"#{o.id} • {prod_name} • {qty} шт. • {fmt_rub(o.total_rub)}"
            f"{' (возврат)' if o.status.value == 'refunded' else ''}"
        )
        rows.append([InlineKeyboardButton(text=label, callback_data=f"hist:{o.id}")])
    await message.answer(
        texts.HISTORY_TITLE,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("hist:"))
async def cb_history_open(callback: CallbackQuery, session: AsyncSession, user: User) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await orders_service.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    items = await orders_service.order_items_with_stock(session, order_id)
    qty = len(items)
    rows = [
        [InlineKeyboardButton(text="📥 Скачать снова", callback_data=f"histdl:{order_id}")]
    ]
    text = (
        f"🧾 <b>Заказ #{order.id}</b>\n"
        f"Кол-во: {qty}\n"
        f"Сумма: {fmt_rub(order.total_rub)}\n"
        f"Статус: {'✅ Оплачено' if order.status.value == 'paid' else '↩️ Возврат'}"
    )
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("histdl:"))
async def cb_history_download(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await orders_service.get_order(session, order_id)
    if order is None or order.user_id != user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    items = await orders_service.order_items_with_stock(session, order_id)
    payloads: list[tuple[str, str]] = []
    for oi, si in items:
        if si is None:
            continue
        v_res = await session.execute(select(Variant).where(Variant.id == oi.variant_id))
        v = v_res.scalar_one_or_none()
        ext = "json"
        prod_name = "item"
        var_name = ""
        if v is not None:
            p_res = await session.execute(select(Product).where(Product.id == v.product_id))
            p = p_res.scalar_one_or_none()
            if p is not None:
                from src.db.models import ProductFormat

                ext = "json" if p.format == ProductFormat.cookies_json else "txt"
                prod_name = p.name
            var_name = v.name
        fname = si.file_name or f"{_safe(prod_name)}_{_safe(var_name)}_{oi.id}.{ext}"
        payloads.append((fname, si.payload))

    if not payloads:
        await callback.answer("Файлы недоступны", show_alert=True)
        return

    if len(payloads) == 1:
        fname, payload = payloads[0]
        await callback.message.answer_document(
            BufferedInputFile(payload.encode("utf-8"), filename=fname)
        )
    else:
        zip_bytes = build_zip_archive(payloads)
        await callback.message.answer_document(
            BufferedInputFile(zip_bytes, filename=f"order_{order_id}.zip")
        )
    await callback.answer()


def _safe(s: str) -> str:
    out = []
    for ch in s or "":
        out.append(ch if ch.isalnum() or ch in "-_" else "_")
    return "".join(out).strip("_") or "item"
