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
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.handlers.admin._filters import AdminFilter
from src.bot.states import AdminVariantStates
from src.services import catalog_service
from src.utils.money import fmt_rub, quantize_rub

router = Router(name="admin_variants")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:vars")
async def cb_vars_root(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session, only_active=False)
    rows = [[InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"adm:varc:{c.id}")] for c in cats]
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "🎚 <b>Варианты</b>\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:varc:"))
async def cb_vars_in_cat(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[2])
    prods = await catalog_service.list_products(session, cat_id, only_active=False)
    rows = [[InlineKeyboardButton(text=f"🛒 {p.name}", callback_data=f"adm:var:list:{p.id}")] for p in prods]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:vars")])
    await callback.message.edit_text(
        "🎚 Выбери товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


def _kb_variants(prod_id: int, variants, counts) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for v in variants:
        toggle = "🟢" if v.is_active else "⭕"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{toggle} {v.name} • {fmt_rub(v.price_rub)} • {counts.get(v.id, 0)} шт.",
                    callback_data=f"adm:var:open:{v.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Новый вариант", callback_data=f"adm:var:new:{prod_id}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"adm:prod:open:{prod_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:var:list:"))
async def cb_var_list(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    variants = await catalog_service.list_variants(session, pid, only_active=False)
    counts = await catalog_service.stock_counts_for_variants(session, [v.id for v in variants])
    prod = await catalog_service.get_product(session, pid)
    title = f"🎚 Варианты «{prod.name if prod else pid}»"
    await callback.message.edit_text(title, reply_markup=_kb_variants(pid, variants, counts))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:var:new:"))
async def cb_var_new(callback: CallbackQuery, state: FSMContext) -> None:
    pid = int(callback.data.split(":")[3])
    await state.set_state(AdminVariantStates.waiting_name)
    await state.update_data(prod_id=pid)
    await callback.message.answer("Введи название варианта:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminVariantStates.waiting_name)
async def msg_var_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(name=name)
    await state.set_state(AdminVariantStates.waiting_price)
    await message.answer("Введи цену в рублях (например 250 или 199.50):")


@router.message(AdminVariantStates.waiting_price)
async def msg_var_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = quantize_rub(Decimal(text))
    except (InvalidOperation, ValueError):
        await message.answer("Цена должна быть числом, например 250 или 199.50.")
        return
    if price <= 0:
        await message.answer("Цена должна быть > 0.")
        return
    data = await state.get_data()
    pid = int(data["prod_id"])
    name = str(data["name"])
    await state.clear()
    v = await catalog_service.create_variant(session, product_id=pid, name=name, price_rub=price)
    await message.answer(f"✅ Вариант «{v.name}» — {fmt_rub(v.price_rub)} создан.")


def _kb_variant_view(v, count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"adm:var:rename:{v.id}")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data=f"adm:var:price:{v.id}")],
        [
            InlineKeyboardButton(
                text="⏸ Скрыть" if v.is_active else "▶️ Показать",
                callback_data=f"adm:var:toggle:{v.id}",
            )
        ],
        [InlineKeyboardButton(text=f"📥 Залить сток ({count})", callback_data=f"adm:upload:var:{v.id}")],
        [InlineKeyboardButton(text="📦 Сток варианта", callback_data=f"adm:stock:var:{v.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:var:del:{v.id}")],
        [InlineKeyboardButton(text="← Назад", callback_data=f"adm:var:list:{v.product_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:var:open:"))
async def cb_var_open(callback: CallbackQuery, session: AsyncSession) -> None:
    vid = int(callback.data.split(":")[3])
    v = await catalog_service.get_variant(session, vid)
    if v is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    count = await catalog_service.stock_count(session, vid)
    await callback.message.edit_text(
        f"🎚 <b>{v.name}</b>\nЦена: {fmt_rub(v.price_rub)}\nВ наличии: {count} шт.",
        parse_mode="HTML",
        reply_markup=_kb_variant_view(v, count),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:var:rename:"))
async def cb_var_rename(callback: CallbackQuery, state: FSMContext) -> None:
    vid = int(callback.data.split(":")[3])
    await state.set_state(AdminVariantStates.waiting_rename)
    await state.update_data(var_id=vid)
    await callback.message.answer("Новое название:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminVariantStates.waiting_rename)
async def msg_var_rename(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = (message.text or "").strip()
    data = await state.get_data()
    vid = int(data["var_id"])
    await state.clear()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await catalog_service.update_variant(session, vid, name=name)
    await message.answer("✅ Переименовано.")


@router.callback_query(F.data.startswith("adm:var:price:"))
async def cb_var_price(callback: CallbackQuery, state: FSMContext) -> None:
    vid = int(callback.data.split(":")[3])
    await state.set_state(AdminVariantStates.waiting_new_price)
    await state.update_data(var_id=vid)
    await callback.message.answer("Новая цена в рублях:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminVariantStates.waiting_new_price)
async def msg_var_new_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = quantize_rub(Decimal(text))
    except (InvalidOperation, ValueError):
        await message.answer("Цена должна быть числом.")
        return
    if price <= 0:
        await message.answer("Цена должна быть > 0.")
        return
    data = await state.get_data()
    vid = int(data["var_id"])
    await state.clear()
    await catalog_service.update_variant(session, vid, price_rub=price)
    await message.answer(f"✅ Новая цена: {fmt_rub(price)}.")


@router.callback_query(F.data.startswith("adm:var:toggle:"))
async def cb_var_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    vid = int(callback.data.split(":")[3])
    v = await catalog_service.get_variant(session, vid)
    if v is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    v = await catalog_service.update_variant(session, vid, is_active=not v.is_active)
    count = await catalog_service.stock_count(session, vid)
    await callback.answer("Статус обновлён")
    await callback.message.edit_text(
        f"🎚 <b>{v.name}</b>\nЦена: {fmt_rub(v.price_rub)}\nВ наличии: {count} шт.",
        parse_mode="HTML",
        reply_markup=_kb_variant_view(v, count),
    )


@router.callback_query(F.data.startswith("adm:var:del:"))
async def cb_var_del(callback: CallbackQuery, session: AsyncSession) -> None:
    vid = int(callback.data.split(":")[3])
    rows = [
        [
            InlineKeyboardButton(text="✅ Удалить", callback_data=f"adm:var:delconf:{vid}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:var:open:{vid}"),
        ]
    ]
    await callback.message.edit_text(
        "Точно удалить вариант со всем стоком?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:var:delconf:"))
async def cb_var_del_conf(callback: CallbackQuery, session: AsyncSession) -> None:
    vid = int(callback.data.split(":")[3])
    v = await catalog_service.get_variant(session, vid)
    pid = v.product_id if v else None
    await catalog_service.delete_variant(session, vid)
    await callback.answer("Удалено")
    if pid is not None:
        variants = await catalog_service.list_variants(session, pid, only_active=False)
        counts = await catalog_service.stock_counts_for_variants(session, [v.id for v in variants])
        await callback.message.edit_text(
            "🎚 Варианты", reply_markup=_kb_variants(pid, variants, counts)
        )
