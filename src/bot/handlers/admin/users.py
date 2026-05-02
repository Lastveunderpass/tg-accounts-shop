from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.handlers.admin._filters import AdminFilter
from src.bot.states import AdminUserStates
from src.db.models import Order, OrderStatus, Topup, TopupStatus
from src.services import users_service
from src.utils.money import fmt_rub, quantize_rub

router = Router(name="admin_users")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:users")
async def cb_users_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminUserStates.waiting_query)
    await callback.message.edit_text(
        "👥 <b>Пользователи</b>\n\nВведи Telegram ID или @username:",
        parse_mode="HTML",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(AdminUserStates.waiting_query)
async def msg_user_query(message: Message, state: FSMContext, session: AsyncSession) -> None:
    q = (message.text or "").strip()
    await state.clear()
    user = None
    if q.lstrip("-").isdigit():
        user = await users_service.get_user(session, int(q))
    elif q.startswith("@"):
        user = await users_service.find_user_by_username(session, q)
    else:
        user = await users_service.find_user_by_username(session, q)
    if user is None:
        await message.answer("Пользователь не найден.")
        return
    await _show_user_card(message, session, user.id)


async def _show_user_card(message_or_cb, session: AsyncSession, user_id: int) -> None:
    user = await users_service.get_user(session, user_id)
    if user is None:
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.answer("Не найден", show_alert=True)
        else:
            await message_or_cb.answer("Не найден")
        return
    purchases = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.user_id == user.id, Order.status == OrderStatus.paid
            )
        )
    ).scalar() or 0
    refunds = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.user_id == user.id, Order.status == OrderStatus.refunded
            )
        )
    ).scalar() or 0
    topups_paid = (
        await session.execute(
            select(func.coalesce(func.sum(Topup.amount_rub), 0)).where(
                Topup.user_id == user.id, Topup.status == TopupStatus.paid
            )
        )
    ).scalar() or 0
    refs = await users_service.referrals_count(session, user.id)

    text = (
        f"👤 <b>Пользователь</b>\n"
        f"ID: <code>{user.id}</code>"
        + (f" @{user.username}" if user.username else "")
        + f"\nИмя: {user.first_name or '—'}\n"
        f"Баланс: <b>{fmt_rub(user.balance_rub)}</b>\n"
        f"Потрачено: <b>{fmt_rub(user.total_spent_rub)}</b>\n"
        f"Пополнений всего: <b>{fmt_rub(topups_paid)}</b>\n"
        f"Покупок: <b>{purchases}</b> (возвратов: {refunds})\n"
        f"Приглашённых: <b>{refs}</b>\n"
        f"Заработано на рефералке: <b>{fmt_rub(user.ref_earned_rub)}</b>\n"
        f"Реф-код: <code>{user.ref_code}</code>\n"
        f"Статус: {'🚫 забанен' if user.is_banned else '✅ активен'}"
    )
    rows = [
        [
            InlineKeyboardButton(text="➕ Баланс", callback_data=f"adm:user:bal:{user.id}:add"),
            InlineKeyboardButton(text="➖ Баланс", callback_data=f"adm:user:bal:{user.id}:sub"),
        ],
        [
            InlineKeyboardButton(
                text="🚫 Забанить" if not user.is_banned else "✅ Разбанить",
                callback_data=f"adm:user:ban:{user.id}",
            )
        ],
        [InlineKeyboardButton(text="🧾 Покупки", callback_data=f"adm:user:orders:{user.id}")],
        [InlineKeyboardButton(text="🔍 Найти другого", callback_data="adm:users")],
        [InlineKeyboardButton(text="← В меню", callback_data="adm:menu")],
    ]
    if isinstance(message_or_cb, CallbackQuery) and message_or_cb.message is not None:
        await message_or_cb.message.edit_text(
            text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
        await message_or_cb.answer()
    else:
        await message_or_cb.answer(
            text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )


@router.callback_query(F.data.startswith("adm:user:bal:"))
async def cb_user_balance(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    user_id = int(parts[3])
    direction = parts[4]
    await state.set_state(AdminUserStates.waiting_balance_delta)
    await state.update_data(user_id=user_id, direction=direction)
    sign = "+" if direction == "add" else "−"
    await callback.message.answer(
        f"Введи сумму ({sign} рублей):", reply_markup=keyboards.cancel_inline()
    )
    await callback.answer()


@router.message(AdminUserStates.waiting_balance_delta)
async def msg_user_balance(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = quantize_rub(Decimal(text))
    except (InvalidOperation, ValueError):
        await message.answer("Введи число.")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть > 0.")
        return
    data = await state.get_data()
    user_id = int(data["user_id"])
    direction = data["direction"]
    await state.clear()
    delta = amount if direction == "add" else -amount
    await users_service.adjust_balance(session, user_id, delta)
    await message.answer("✅ Баланс изменён.")
    await _show_user_card(message, session, user_id)


@router.callback_query(F.data.startswith("adm:user:ban:"))
async def cb_user_ban(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[3])
    user = await users_service.get_user(session, user_id)
    if user is None:
        await callback.answer("Не найден", show_alert=True)
        return
    await users_service.set_banned(session, user_id, not user.is_banned)
    await callback.answer("Готово")
    await _show_user_card(callback, session, user_id)


@router.callback_query(F.data.startswith("adm:user:orders:"))
async def cb_user_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[3])
    res = await session.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(20)
    )
    orders = list(res.scalars().all())
    if not orders:
        await callback.answer("Нет покупок", show_alert=True)
        return
    rows = []
    for o in orders:
        status = "✅" if o.status == OrderStatus.paid else "↩️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} #{o.id} • {fmt_rub(o.total_rub)} • {o.created_at:%Y-%m-%d}",
                    callback_data=f"adm:order:open:{o.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"adm:user:back:{user_id}")])
    await callback.message.edit_text(
        f"🧾 Покупки <code>{user_id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:user:back:"))
async def cb_user_back(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[3])
    await _show_user_card(callback, session, user_id)
