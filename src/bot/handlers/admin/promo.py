from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.handlers.admin._filters import AdminFilter
from src.bot.states import AdminPromoStates
from src.db.models import PromoCode, PromoScope, PromoType
from src.services import promo_service
from src.utils.money import fmt_rub, quantize_rub

router = Router(name="admin_promo")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:promos")
async def cb_promos_root(callback: CallbackQuery, session: AsyncSession) -> None:
    promos = await promo_service.list_promos(session, only_active=False)
    rows: list[list[InlineKeyboardButton]] = []
    for p in promos[:20]:
        flag = "🟢" if p.is_active else "⭕"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{flag} {p.code} • {p.type.value} • {p.value}",
                    callback_data=f"adm:promo:open:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Новый промокод", callback_data="adm:promo:new")])
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "🎟 <b>Промокоды</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:promo:new")
async def cb_promo_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPromoStates.waiting_code)
    await callback.message.answer(
        "Введи код промокода (например <code>WELCOME10</code>):",
        parse_mode="HTML",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(AdminPromoStates.waiting_code)
async def msg_promo_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer("Код не может быть пустым.")
        return
    await state.update_data(code=code)
    await state.set_state(AdminPromoStates.waiting_type)
    rows = [
        [InlineKeyboardButton(text="% скидка на покупку", callback_data="adm:promo:type:percent")],
        [InlineKeyboardButton(text="₽ скидка на покупку", callback_data="adm:promo:type:fixed")],
        [InlineKeyboardButton(text="💰 На баланс", callback_data="adm:promo:type:balance")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ]
    await message.answer(
        "Тип промокода:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(AdminPromoStates.waiting_type, F.data.startswith("adm:promo:type:"))
async def cb_promo_type(callback: CallbackQuery, state: FSMContext) -> None:
    type_val = callback.data.split(":")[3]
    await state.update_data(type=type_val)
    await state.set_state(AdminPromoStates.waiting_value)
    if type_val == "percent":
        prompt = "Введи процент (1–100):"
    elif type_val == "fixed":
        prompt = "Введи сумму скидки в рублях:"
    else:
        prompt = "Введи сумму бонуса на баланс в рублях:"
    await callback.message.answer(prompt, reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminPromoStates.waiting_value)
async def msg_promo_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        value = quantize_rub(Decimal(text))
    except (InvalidOperation, ValueError):
        await message.answer("Нужно число.")
        return
    if value <= 0:
        await message.answer("Должно быть > 0.")
        return
    data = await state.get_data()
    type_val = str(data["type"])
    if type_val == "percent" and value > 100:
        await message.answer("Процент не может быть > 100.")
        return
    code = str(data["code"])
    try:
        promo = await promo_service.create_promo(
            session,
            code=code,
            type_=PromoType(type_val),
            value=value,
            scope=PromoScope.all,
        )
    except promo_service.PromoError as e:
        await state.clear()
        await message.answer(f"❌ {e}")
        return
    await state.clear()
    await message.answer(
        f"✅ Промокод <code>{promo.code}</code> создан.\n"
        "По умолчанию: scope=all, без лимитов и срока. Откорректируй в карточке.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("adm:promo:open:"))
async def cb_promo_open(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    p = await session.get(PromoCode, pid)
    if p is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    expires = p.expires_at.strftime("%Y-%m-%d") if p.expires_at else "—"
    text = (
        f"🎟 <b>{p.code}</b>\n"
        f"Тип: <code>{p.type.value}</code>\n"
        f"Значение: <b>{p.value}</b>\n"
        f"Использован: {p.used_count}"
        + (f" / {p.max_uses}" if p.max_uses else "")
        + f"\nЛимит на юзера: {p.max_uses_per_user or '—'}\n"
        f"Истекает: {expires}\n"
        f"Минимум заказа: {fmt_rub(p.min_order_rub) if p.min_order_rub else '—'}\n"
        f"Scope: {p.scope.value}"
        + (f" (id={p.scope_id})" if p.scope_id else "")
        + f"\nСтатус: {'🟢' if p.is_active else '⭕'}"
    )
    rows = [
        [InlineKeyboardButton(text="📅 Срок 7 дней", callback_data=f"adm:promo:exp7:{p.id}")],
        [InlineKeyboardButton(text="📅 Срок 30 дней", callback_data=f"adm:promo:exp30:{p.id}")],
        [InlineKeyboardButton(text="∞ Убрать срок", callback_data=f"adm:promo:expnone:{p.id}")],
        [
            InlineKeyboardButton(
                text=("⏸ Деактивировать" if p.is_active else "▶️ Активировать"),
                callback_data=f"adm:promo:toggle:{p.id}",
            )
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:promo:del:{p.id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="adm:promos")],
    ]
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


async def _set_expiry(session: AsyncSession, promo_id: int, days: int | None) -> None:
    p = await session.get(PromoCode, promo_id)
    if p is None:
        return
    p.expires_at = (datetime.now(UTC) + timedelta(days=days)) if days else None
    await session.flush()


@router.callback_query(F.data.startswith("adm:promo:exp7:"))
async def cb_promo_exp7(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    await _set_expiry(session, pid, 7)
    await callback.answer("Срок: 7 дней")
    await cb_promo_open_internal(callback, session, pid)


@router.callback_query(F.data.startswith("adm:promo:exp30:"))
async def cb_promo_exp30(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    await _set_expiry(session, pid, 30)
    await callback.answer("Срок: 30 дней")
    await cb_promo_open_internal(callback, session, pid)


@router.callback_query(F.data.startswith("adm:promo:expnone:"))
async def cb_promo_expnone(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    await _set_expiry(session, pid, None)
    await callback.answer("Бессрочно")
    await cb_promo_open_internal(callback, session, pid)


async def cb_promo_open_internal(callback: CallbackQuery, session: AsyncSession, pid: int) -> None:
    callback.data = f"adm:promo:open:{pid}"  # хак для повторного вызова
    await cb_promo_open(callback, session)


@router.callback_query(F.data.startswith("adm:promo:toggle:"))
async def cb_promo_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    p = await session.get(PromoCode, pid)
    if p is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    p.is_active = not p.is_active
    await session.flush()
    await callback.answer("Готово")
    await cb_promo_open_internal(callback, session, pid)


@router.callback_query(F.data.startswith("adm:promo:del:"))
async def cb_promo_del(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    await promo_service.delete_promo(session, pid)
    await callback.answer("Удалён")
    await cb_promos_root(callback, session)
