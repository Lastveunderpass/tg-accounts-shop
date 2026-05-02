from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot import texts
from src.bot.handlers.admin._filters import AdminFilter

router = Router(name="admin_menu")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def admin_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="📁 Категории", callback_data="adm:cats"),
            InlineKeyboardButton(text="🛒 Товары", callback_data="adm:prods"),
        ],
        [
            InlineKeyboardButton(text="🎚 Варианты", callback_data="adm:vars"),
            InlineKeyboardButton(text="📥 Залить сток", callback_data="adm:upload"),
        ],
        [
            InlineKeyboardButton(text="📦 Сток", callback_data="adm:stock"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton(text="🧾 Покупки", callback_data="adm:orders"),
            InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm:promos"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
            InlineKeyboardButton(text="📣 Рассылка", callback_data="adm:bcast"),
        ],
        [
            InlineKeyboardButton(text="👋 Приветствие", callback_data="adm:welcome"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == texts.MENU_ADMIN)
async def admin_root(message: Message) -> None:
    await message.answer("👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def cb_admin_root(callback: CallbackQuery) -> None:
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                "👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu_kb()
            )
        except Exception:
            await callback.message.answer(
                "👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu_kb()
            )
    await callback.answer()
