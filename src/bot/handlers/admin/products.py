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
from src.bot.states import AdminProductStates
from src.db.models import ProductFormat, UploadMode
from src.services import catalog_service

router = Router(name="admin_products")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _kb_categories_for_products(cats) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in cats:
        rows.append([InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"adm:prod:cat:{c.id}")])
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:prods")
async def cb_products_root(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session, only_active=False)
    if not cats:
        await callback.message.edit_text(
            "Нет категорий. Сначала создай категорию.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="← В меню", callback_data="adm:menu")]]
            ),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "🛒 <b>Товары</b>\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=_kb_categories_for_products(cats),
    )
    await callback.answer()


def _kb_products(cat_id: int, prods) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in prods:
        toggle = "🟢" if p.is_active else "⭕"
        rows.append(
            [InlineKeyboardButton(text=f"{toggle} {p.name}", callback_data=f"adm:prod:open:{p.id}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Новый товар", callback_data=f"adm:prod:new:{cat_id}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:prods")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:prod:cat:"))
async def cb_products_in_category(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[3])
    prods = await catalog_service.list_products(session, cat_id, only_active=False)
    cat = await catalog_service.get_category(session, cat_id)
    title = f"🛒 Товары в «{cat.name if cat else cat_id}»"
    await callback.message.edit_text(title, reply_markup=_kb_products(cat_id, prods))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:new:"))
async def cb_new_product(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[3])
    await state.set_state(AdminProductStates.waiting_name)
    await state.update_data(cat_id=cat_id)
    await callback.message.answer("Введи название товара:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminProductStates.waiting_name)
async def msg_new_product_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    data = await state.get_data()
    cat_id = int(data["cat_id"])
    prod = await catalog_service.create_product(session, category_id=cat_id, name=name)
    await state.clear()
    await message.answer(
        f"✅ Товар «{prod.name}» создан. Настрой формат и режим заливки.",
        reply_markup=_kb_product_view(prod),
    )


def _kb_product_view(prod) -> InlineKeyboardMarkup:
    fmt_label = {
        ProductFormat.cookies_json: "JSON cookies",
        ProductFormat.login_pass: "login:pass",
        ProductFormat.custom_text: "Произвольный текст",
    }[prod.format]
    upload_label = {
        UploadMode.zip_files: "ZIP с файлами",
        UploadMode.line_per_unit: "По строкам",
        UploadMode.media_group: "Несколько документов",
    }[prod.upload_mode]
    image_label = "🖼 Картинка: есть" if prod.image_file_id else "🖼 Картинка: нет"
    rows = [
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"adm:prod:rename:{prod.id}")],
        [InlineKeyboardButton(text="📝 Описание", callback_data=f"adm:prod:desc:{prod.id}")],
        [InlineKeyboardButton(text=image_label, callback_data=f"adm:prod:img:{prod.id}")],
        [
            InlineKeyboardButton(
                text=f"🧬 Формат: {fmt_label}", callback_data=f"adm:prod:fmt:{prod.id}"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📥 Заливка: {upload_label}",
                callback_data=f"adm:prod:upload:{prod.id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⏸ Скрыть" if prod.is_active else "▶️ Показать",
                callback_data=f"adm:prod:toggle:{prod.id}",
            )
        ],
        [InlineKeyboardButton(text="🎚 Варианты", callback_data=f"adm:var:list:{prod.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:prod:del:{prod.id}")],
        [InlineKeyboardButton(text="← Назад", callback_data=f"adm:prod:cat:{prod.category_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm:prod:open:"))
async def cb_open_product(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    desc = f"\n\n{prod.description}" if prod.description else ""
    await callback.message.edit_text(
        f"🛒 <b>{prod.name}</b>{desc}", parse_mode="HTML", reply_markup=_kb_product_view(prod)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:rename:"))
async def cb_rename_product(callback: CallbackQuery, state: FSMContext) -> None:
    pid = int(callback.data.split(":")[3])
    await state.set_state(AdminProductStates.waiting_rename)
    await state.update_data(prod_id=pid)
    await callback.message.answer("Введи новое название:", reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(AdminProductStates.waiting_rename)
async def msg_rename_product(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = (message.text or "").strip()
    data = await state.get_data()
    pid = int(data["prod_id"])
    await state.clear()
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await catalog_service.update_product(session, pid, name=name)
    await message.answer("✅ Переименовано.")


@router.callback_query(F.data.startswith("adm:prod:desc:"))
async def cb_desc_product(callback: CallbackQuery, state: FSMContext) -> None:
    pid = int(callback.data.split(":")[3])
    await state.set_state(AdminProductStates.waiting_description)
    await state.update_data(prod_id=pid)
    await callback.message.answer(
        "Введи новое описание (или «-» чтобы очистить):", reply_markup=keyboards.cancel_inline()
    )
    await callback.answer()


@router.message(AdminProductStates.waiting_description)
async def msg_desc_product(message: Message, state: FSMContext, session: AsyncSession) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    data = await state.get_data()
    pid = int(data["prod_id"])
    await state.clear()
    await catalog_service.update_product(session, pid, description=desc or None)
    await message.answer("✅ Описание обновлено.")


@router.callback_query(F.data.startswith("adm:prod:img:"))
async def cb_image_product(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    pid = int(callback.data.split(":")[3])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    rows: list[list[InlineKeyboardButton]] = []
    if prod.image_file_id:
        rows.append(
            [InlineKeyboardButton(text="🗑 Убрать картинку", callback_data=f"adm:prod:imgdel:{pid}")]
        )
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"adm:prod:open:{pid}")])
    await state.set_state(AdminProductStates.waiting_image)
    await state.update_data(prod_id=pid)
    await callback.message.answer(
        "Пришли картинку товара одним фото-сообщением. Она появится в каталоге.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.message(AdminProductStates.waiting_image, F.photo)
async def msg_product_image_photo(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    pid = int(data["prod_id"])
    file_id = message.photo[-1].file_id
    prod = await catalog_service.update_product(session, pid, image_file_id=file_id)
    await state.clear()
    await message.answer("✅ Картинка обновлена.", reply_markup=_kb_product_view(prod))


@router.message(AdminProductStates.waiting_image)
async def msg_product_image_invalid(message: Message) -> None:
    await message.answer("Нужно прислать именно фото (не файл).")


@router.callback_query(F.data.startswith("adm:prod:imgdel:"))
async def cb_image_product_delete(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    pid = int(callback.data.split(":")[3])
    prod = await catalog_service.update_product(session, pid, image_file_id=None)
    await state.clear()
    await callback.answer("Картинка удалена")
    await callback.message.edit_text(
        f"🛒 <b>{prod.name}</b>", parse_mode="HTML", reply_markup=_kb_product_view(prod)
    )


@router.callback_query(F.data.startswith("adm:prod:fmt:"))
async def cb_fmt_product(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    rows = [
        [InlineKeyboardButton(text="JSON cookies", callback_data=f"adm:prod:fmtset:{pid}:cookies_json")],
        [InlineKeyboardButton(text="login:pass", callback_data=f"adm:prod:fmtset:{pid}:login_pass")],
        [InlineKeyboardButton(text="Произвольный текст", callback_data=f"adm:prod:fmtset:{pid}:custom_text")],
        [InlineKeyboardButton(text="← Назад", callback_data=f"adm:prod:open:{pid}")],
    ]
    await callback.message.edit_text(
        "Выбери формат содержимого аккаунта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:fmtset:"))
async def cb_fmt_set(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    pid = int(parts[3])
    fmt_val = parts[4]
    fmt = ProductFormat(fmt_val)
    prod = await catalog_service.update_product(session, pid, fmt=fmt)
    await callback.answer("Обновлено")
    await callback.message.edit_text(
        f"🛒 <b>{prod.name}</b>", parse_mode="HTML", reply_markup=_kb_product_view(prod)
    )


@router.callback_query(F.data.startswith("adm:prod:upload:"))
async def cb_upload_product(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    rows = [
        [InlineKeyboardButton(text="ZIP с файлами", callback_data=f"adm:prod:upset:{pid}:zip_files")],
        [InlineKeyboardButton(text="По строкам", callback_data=f"adm:prod:upset:{pid}:line_per_unit")],
        [InlineKeyboardButton(text="Несколько документов", callback_data=f"adm:prod:upset:{pid}:media_group")],
        [InlineKeyboardButton(text="← Назад", callback_data=f"adm:prod:open:{pid}")],
    ]
    await callback.message.edit_text(
        "Как админ будет заливать сток для этого товара:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:upset:"))
async def cb_upload_set(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    pid = int(parts[3])
    mode_val = parts[4]
    mode = UploadMode(mode_val)
    prod = await catalog_service.update_product(session, pid, upload_mode=mode)
    await callback.answer("Обновлено")
    await callback.message.edit_text(
        f"🛒 <b>{prod.name}</b>", parse_mode="HTML", reply_markup=_kb_product_view(prod)
    )


@router.callback_query(F.data.startswith("adm:prod:toggle:"))
async def cb_toggle_product(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    prod = await catalog_service.update_product(session, pid, is_active=not prod.is_active)
    await callback.answer("Статус обновлён")
    await callback.message.edit_text(
        f"🛒 <b>{prod.name}</b>", parse_mode="HTML", reply_markup=_kb_product_view(prod)
    )


@router.callback_query(F.data.startswith("adm:prod:del:"))
async def cb_delete_product(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    rows = [
        [
            InlineKeyboardButton(text="✅ Удалить", callback_data=f"adm:prod:delconf:{pid}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:prod:open:{pid}"),
        ]
    ]
    await callback.message.edit_text(
        "Точно удалить товар вместе со всеми вариантами и стоком?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:prod:delconf:"))
async def cb_delete_product_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[3])
    prod = await catalog_service.get_product(session, pid)
    cat_id = prod.category_id if prod else None
    await catalog_service.delete_product(session, pid)
    await callback.answer("Удалено")
    if cat_id is not None:
        prods = await catalog_service.list_products(session, cat_id, only_active=False)
        await callback.message.edit_text(
            "🛒 Товары", reply_markup=_kb_products(cat_id, prods)
        )
