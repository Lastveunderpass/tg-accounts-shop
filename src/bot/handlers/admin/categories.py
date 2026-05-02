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
from src.bot.states import AdminCategoryStates
from src.services import catalog_service

router = Router(name="admin_categories")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _kb_categories(cats) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in cats:
        toggle = "🟢" if c.is_active else "⭕"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{toggle} {c.name}", callback_data=f"adm:cat:open:{c.id}"
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Создать категорию", callback_data="adm:cat:new")])
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:cats")
async def cb_list_categories(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session, only_active=False)
    if callback.message is not None:
        await callback.message.edit_text(
            "📁 <b>Категории</b>", parse_mode="HTML", reply_markup=_kb_categories(cats)
        )
    await callback.answer()


@router.callback_query(F.data == "adm:cat:new")
async def cb_new_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminCategoryStates.waiting_name)
    await callback.message.answer("Введи название категории:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminCategoryStates.waiting_name)
async def msg_new_category(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = (message.text or "").strip()
    await state.clear()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    cat = await catalog_service.create_category(session, name=name)
    await message.answer(f"✅ Категория «{cat.name}» создана.")
    cats = await catalog_service.list_categories(session, only_active=False)
    await message.answer("📁 <b>Категории</b>", parse_mode="HTML", reply_markup=_kb_categories(cats))


@router.callback_query(F.data.startswith("adm:cat:open:"))
async def cb_open_category(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[3])
    cat = await catalog_service.get_category(session, cat_id)
    if cat is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    rows = [
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"adm:cat:rename:{cat.id}")],
        [
            InlineKeyboardButton(
                text="⏸ Скрыть" if cat.is_active else "▶️ Показать",
                callback_data=f"adm:cat:toggle:{cat.id}",
            )
        ],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:cat:del:{cat.id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="adm:cats")],
    ]
    await callback.message.edit_text(
        f"📁 <b>{cat.name}</b>\nСтатус: {'🟢 активна' if cat.is_active else '⭕ скрыта'}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cat:rename:"))
async def cb_rename_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[3])
    await state.set_state(AdminCategoryStates.waiting_rename)
    await state.update_data(cat_id=cat_id)
    await callback.message.answer("Введи новое название:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminCategoryStates.waiting_rename)
async def msg_rename_category(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cat_id = int(data["cat_id"])
    name = (message.text or "").strip()
    await state.clear()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await catalog_service.update_category(session, cat_id, name=name)
    await message.answer("✅ Переименовано.")


@router.callback_query(F.data.startswith("adm:cat:toggle:"))
async def cb_toggle_category(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[3])
    cat = await catalog_service.get_category(session, cat_id)
    if cat is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    await catalog_service.update_category(session, cat_id, is_active=not cat.is_active)
    await callback.answer("Статус обновлён")
    cats = await catalog_service.list_categories(session, only_active=False)
    await callback.message.edit_text(
        "📁 <b>Категории</b>", parse_mode="HTML", reply_markup=_kb_categories(cats)
    )


@router.callback_query(F.data.startswith("adm:cat:del:"))
async def cb_delete_category(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[3])
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Удалить", callback_data=f"adm:cat:delconf:{cat_id}"
            ),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:cat:open:{cat_id}"),
        ]
    ]
    await callback.message.edit_text(
        "Точно удалить категорию вместе со всеми товарами и стоком?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cat:delconf:"))
async def cb_delete_category_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[3])
    await catalog_service.delete_category(session, cat_id)
    await callback.answer("Удалено")
    cats = await catalog_service.list_categories(session, only_active=False)
    await callback.message.edit_text(
        "📁 <b>Категории</b>", parse_mode="HTML", reply_markup=_kb_categories(cats)
    )
