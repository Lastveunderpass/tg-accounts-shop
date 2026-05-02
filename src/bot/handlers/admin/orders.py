from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.admin._filters import AdminFilter
from src.db.models import Order, OrderStatus, Product, Variant
from src.services import orders_service
from src.services.notifications import notify_admin
from src.services.orders_service import OrderError
from src.utils.money import fmt_rub

router = Router(name="admin_orders")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:orders")
async def cb_orders_root(callback: CallbackQuery, session: AsyncSession) -> None:
    res = await session.execute(select(Order).order_by(Order.id.desc()).limit(20))
    orders = list(res.scalars().all())
    if not orders:
        await callback.message.edit_text(
            "Покупок пока нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← В меню", callback_data="adm:menu")]]
            ),
        )
        await callback.answer()
        return
    rows = []
    for o in orders:
        status = "✅" if o.status == OrderStatus.paid else "↩️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} #{o.id} • {fmt_rub(o.total_rub)} • user {o.user_id}",
                    callback_data=f"adm:order:open:{o.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "🧾 <b>Последние покупки</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:order:open:"))
async def cb_order_open(callback: CallbackQuery, session: AsyncSession) -> None:
    oid = int(callback.data.split(":")[3])
    order = await orders_service.get_order(session, oid)
    if order is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    items = await orders_service.order_items_with_stock(session, oid)
    lines: list[str] = []
    for oi, _si in items:
        v_res = await session.execute(select(Variant).where(Variant.id == oi.variant_id))
        v = v_res.scalar_one_or_none()
        prod_name = ""
        if v is not None:
            p_res = await session.execute(select(Product).where(Product.id == v.product_id))
            p = p_res.scalar_one_or_none()
            prod_name = p.name if p else ""
        lines.append(f"• {prod_name} / {v.name if v else '?'} — {fmt_rub(oi.unit_price_rub)}")
    text = (
        f"🧾 <b>Заказ #{order.id}</b>\n"
        f"User: <code>{order.user_id}</code>\n"
        f"Статус: {'✅ оплачен' if order.status == OrderStatus.paid else '↩️ возврат'}\n"
        f"Сумма: {fmt_rub(order.total_rub)}\n"
        f"Скидка: {fmt_rub(order.discount_rub)}\n"
        f"Дата: {order.created_at:%Y-%m-%d %H:%M}\n\n"
        + "\n".join(lines)
    )
    rows: list[list[InlineKeyboardButton]] = []
    if order.status == OrderStatus.paid:
        rows.append(
            [InlineKeyboardButton(text="↩️ Возврат", callback_data=f"adm:order:refund:{oid}")]
        )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:orders")])
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:order:refund:"))
async def cb_order_refund(callback: CallbackQuery, state: FSMContext) -> None:
    oid = int(callback.data.split(":")[3])
    rows = [
        [
            InlineKeyboardButton(
                text="💰 Деньги + товар обратно", callback_data=f"adm:refund:both:{oid}"
            )
        ],
        [InlineKeyboardButton(text="💰 Только деньги", callback_data=f"adm:refund:money:{oid}")],
        [InlineKeyboardButton(text="🔁 Только заменить (TODO ручное)", callback_data="adm:refund:noop")],
        [InlineKeyboardButton(text="← Отмена", callback_data=f"adm:order:open:{oid}")],
    ]
    await callback.message.edit_text(
        "Выбери тип возврата:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data == "adm:refund:noop")
async def cb_refund_noop(callback: CallbackQuery) -> None:
    await callback.answer(
        "Замена делается вручную через выдачу нового аккаунта (Пользователи → +Баланс или ручная пересылка).",
        show_alert=True,
    )


async def _do_refund(
    callback: CallbackQuery,
    session: AsyncSession,
    order_id: int,
    *,
    return_money: bool,
    return_stock: bool,
    note: str | None = None,
) -> None:
    try:
        order = await orders_service.refund_order(
            session,
            order_id=order_id,
            admin_id=callback.from_user.id if callback.from_user else 0,
            return_money=return_money,
            return_stock=return_stock,
            note=note,
        )
    except OrderError as e:
        await callback.message.answer(f"❌ {e}")
        await callback.answer()
        return

    bot = callback.bot
    if bot is not None:
        await notify_admin(
            bot,
            f"↩️ Возврат заказа #{order.id} • {fmt_rub(order.total_rub)} • user <code>{order.user_id}</code>",
            key="notify_refund",
        )
        try:
            await bot.send_message(
                order.user_id,
                f"↩️ Заказ #{order.id} возвращён."
                + (f" На баланс возвращено: <b>{fmt_rub(order.total_rub)}</b>" if return_money else ""),
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.message.edit_text(f"✅ Возврат для #{order.id} оформлен.")
    await callback.answer()


@router.callback_query(F.data.startswith("adm:refund:both:"))
async def cb_refund_both(callback: CallbackQuery, session: AsyncSession) -> None:
    oid = int(callback.data.split(":")[3])
    await _do_refund(callback, session, oid, return_money=True, return_stock=True)


@router.callback_query(F.data.startswith("adm:refund:money:"))
async def cb_refund_money(callback: CallbackQuery, session: AsyncSession) -> None:
    oid = int(callback.data.split(":")[3])
    await _do_refund(callback, session, oid, return_money=True, return_stock=False)
