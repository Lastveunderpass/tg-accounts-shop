from __future__ import annotations

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
from src.bot.states import AdminSettingsStates
from src.services import settings_service

router = Router(name="admin_settings")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


SETTING_DEFS: list[tuple[str, str, str]] = [
    ("referral_percent", "Реф %", "int"),
    ("min_topup_rub", "Мин. пополнение, ₽", "int"),
    ("stock_low_threshold", "Порог низкого стока", "int"),
    ("max_qty_per_order", "Макс. шт. за заказ", "int"),
    ("cryptobot_enabled", "Оплата через CryptoBot", "bool"),
    ("lolzteam_enabled", "Оплата через Lolzteam", "bool"),
    ("lolzteam_surcharge_percent", "Lolzteam — наценка, %", "decimal"),
    ("notify_new_user", "Уведомлять о новых юзерах", "bool"),
    ("notify_new_topup", "Уведомлять о пополнениях", "bool"),
    ("notify_new_purchase", "Уведомлять о покупках", "bool"),
    ("notify_low_stock", "Уведомлять о низком стоке", "bool"),
    ("notify_refund", "Уведомлять о возвратах", "bool"),
    ("debug_mode", "Debug-режим (ошибки в ЛС)", "bool"),
]


@router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    rows: list[list[InlineKeyboardButton]] = []
    all_set = await settings_service.all_settings(session)
    for key, label, kind in SETTING_DEFS:
        cur = all_set.get(key, "")
        if kind == "bool":
            display = "🟢" if cur in ("1", "true", "True", "on") else "⭕"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{display} {label}", callback_data=f"adm:set:tog:{key}"
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{label}: {cur}", callback_data=f"adm:set:edit:{key}"
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n(меняются на лету, без рестарта)",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:set:tog:"))
async def cb_setting_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    key = callback.data.split(":")[3]
    cur = await settings_service.get_bool(session, key, False)
    await settings_service.set_setting(session, key, "0" if cur else "1")
    await callback.answer("Готово")
    await cb_settings(callback, session)


@router.callback_query(F.data.startswith("adm:set:edit:"))
async def cb_setting_edit(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[3]
    await state.set_state(AdminSettingsStates.waiting_value)
    await state.update_data(key=key)
    await callback.message.answer(f"Введи новое значение для <code>{key}</code>:", parse_mode="HTML",
                                  reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminSettingsStates.waiting_value)
async def msg_setting_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    val = (message.text or "").strip()
    data = await state.get_data()
    key = str(data["key"])
    await state.clear()
    if not val:
        await message.answer("Пусто — отмена.")
        return
    await settings_service.set_setting(session, key, val)
    await message.answer(f"✅ <code>{key}</code> = <code>{val}</code>", parse_mode="HTML")
