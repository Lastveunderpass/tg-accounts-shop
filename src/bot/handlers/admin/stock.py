from __future__ import annotations

import asyncio
from datetime import UTC

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
from src.bot.states import AdminStockStates
from src.db.models import StockSubscription, UploadMode
from src.services import catalog_service, stock_service
from src.services.notifications import notify_admin
from src.utils.parsers import (
    ParseError,
    parse_line_based,
    parse_single_file,
    parse_zip_archive,
)

router = Router(name="admin_stock")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


# ───────────────────── Меню «Залить сток» ─────────────────────
@router.callback_query(F.data == "adm:upload")
async def cb_upload_root(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session, only_active=False)
    rows = [[InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"adm:upcat:{c.id}")] for c in cats]
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "📥 <b>Залить сток</b>\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upcat:"))
async def cb_upload_cat(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[2])
    prods = await catalog_service.list_products(session, cat_id, only_active=False)
    rows = [
        [InlineKeyboardButton(text=f"🛒 {p.name}", callback_data=f"adm:upprod:{p.id}")] for p in prods
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:upload")])
    await callback.message.edit_text(
        "Выбери товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upprod:"))
async def cb_upload_prod(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[2])
    variants = await catalog_service.list_variants(session, pid, only_active=False)
    rows = [
        [InlineKeyboardButton(text=f"🎚 {v.name}", callback_data=f"adm:upload:var:{v.id}")]
        for v in variants
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:upload")])
    await callback.message.edit_text(
        "Выбери вариант:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:upload:var:"))
async def cb_upload_var(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    vid = int(callback.data.split(":")[3])
    v = await catalog_service.get_variant(session, vid)
    if v is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    prod = await catalog_service.get_product(session, v.product_id)
    if prod is None:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await state.set_state(AdminStockStates.waiting_upload)
    await state.update_data(variant_id=vid, product_id=prod.id, upload_mode=prod.upload_mode.value)

    if prod.upload_mode == UploadMode.zip_files:
        text = (
            "📥 Пришли <b>ZIP-архив</b> с файлами.\n"
            "Каждый файл в архиве = 1 аккаунт.\n"
            "JSON может быть многострочным — содержимое сохраняется как есть."
        )
    elif prod.upload_mode == UploadMode.line_per_unit:
        text = (
            "📥 Пришли <b>.txt-файл</b> или просто текст в сообщении.\n"
            "Каждая непустая строка = 1 аккаунт."
        )
    else:
        text = (
            "📥 Пришли <b>один или несколько документов</b> одним сообщением (media group).\n"
            "Каждый файл = 1 аккаунт."
        )

    await callback.message.answer(
        text, parse_mode="HTML", reply_markup=keyboards.cancel_inline()
    )
    await callback.answer()


# ───────────────────── Приём заливки ─────────────────────
async def _handle_zip(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.document is None:
        await message.answer("Жду ZIP-файл.")
        return
    bot = message.bot
    file = await bot.get_file(message.document.file_id)
    bio = await bot.download_file(file.file_path)
    if bio is None:
        await message.answer("Не удалось скачать файл.")
        return
    content = bio.read()

    data = await state.get_data()
    pid = int(data["product_id"])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    try:
        items = parse_zip_archive(content, prod.format)
    except ParseError as e:
        await message.answer(f"❌ {e}")
        return

    await _confirm_items(message, state, items)


async def _handle_line_text(
    message: Message, state: FSMContext, session: AsyncSession, text: str
) -> None:
    data = await state.get_data()
    pid = int(data["product_id"])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    try:
        items = parse_line_based(text, prod.format)
    except ParseError as e:
        await message.answer(f"❌ {e}")
        return
    await _confirm_items(message, state, items)


async def _handle_line_file(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.document is None:
        return
    bot = message.bot
    file = await bot.get_file(message.document.file_id)
    bio = await bot.download_file(file.file_path)
    if bio is None:
        await message.answer("Не удалось скачать файл.")
        return
    try:
        text = bio.read().decode("utf-8")
    except UnicodeDecodeError:
        await message.answer("❌ Файл не в UTF-8.")
        return
    await _handle_line_text(message, state, session, text)


async def _handle_single_doc(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if message.document is None:
        return
    bot = message.bot
    file = await bot.get_file(message.document.file_id)
    bio = await bot.download_file(file.file_path)
    if bio is None:
        await message.answer("Не удалось скачать файл.")
        return
    content = bio.read()
    data = await state.get_data()
    pid = int(data["product_id"])
    prod = await catalog_service.get_product(session, pid)
    if prod is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    try:
        item = parse_single_file(message.document.file_name or "file", content, prod.format)
    except ParseError as e:
        await message.answer(f"❌ {e}")
        return

    # Группируем по media_group_id, если присутствует
    pending: list = list(data.get("pending_items") or [])
    pending.append({"payload": item.payload, "file_name": item.file_name})
    await state.update_data(pending_items=pending)

    if message.media_group_id is None:
        # одиночный документ — сразу подтверждаем
        items = [_dict_to_parsed(p) for p in pending]
        await state.update_data(pending_items=[])
        await _confirm_items(message, state, items)
    else:
        # ждём остальные документы из группы (Telegram доставляет ~ за 1-2 сек)
        await state.update_data(media_group_id=message.media_group_id)
        await asyncio.sleep(1.2)
        # перепроверяем — если за это время никто не добавил, считаем что группа полная
        fresh = await state.get_data()
        if fresh.get("media_group_id") == message.media_group_id:
            items = [_dict_to_parsed(p) for p in fresh.get("pending_items", [])]
            await state.update_data(pending_items=[], media_group_id=None)
            if items:
                await _confirm_items(message, state, items)


def _dict_to_parsed(d):
    from src.utils.parsers import ParsedItem

    return ParsedItem(payload=d["payload"], file_name=d.get("file_name"))


async def _confirm_items(message: Message, state: FSMContext, items: list) -> None:
    await state.update_data(parsed=[{"payload": i.payload, "file_name": i.file_name} for i in items])
    await state.set_state(AdminStockStates.confirming)

    preview = "\n".join(
        f"• {i.file_name or '(no name)'}: {(i.payload[:60] + '…') if len(i.payload) > 60 else i.payload}"
        for i in items[:3]
    )
    rows = [
        [
            InlineKeyboardButton(text="✅ Залить", callback_data="adm:upload:commit"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]
    ]
    await message.answer(
        f"📦 Найдено аккаунтов: <b>{len(items)}</b>\n\n"
        f"Превью первых:\n<pre>{preview}</pre>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(AdminStockStates.waiting_upload)
async def msg_upload(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    upload_mode = data.get("upload_mode")
    if upload_mode == UploadMode.zip_files.value:
        if message.document is None:
            await message.answer("Жду ZIP-файл.")
            return
        await _handle_zip(message, state, session)
    elif upload_mode == UploadMode.line_per_unit.value:
        if message.document is not None:
            await _handle_line_file(message, state, session)
        elif message.text:
            await _handle_line_text(message, state, session, message.text)
        else:
            await message.answer("Жду .txt-файл или текст.")
    else:  # media_group
        if message.document is None:
            await message.answer("Жду документ(ы).")
            return
        await _handle_single_doc(message, state, session)


@router.callback_query(AdminStockStates.confirming, F.data == "adm:upload:commit")
async def cb_upload_commit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    var_id = int(data["variant_id"])
    parsed = data.get("parsed", [])
    items = [_dict_to_parsed(p) for p in parsed]
    if not items:
        await callback.answer("Пусто", show_alert=True)
        await state.clear()
        return

    admin_id = callback.from_user.id if callback.from_user else 0
    batch = await stock_service.add_stock_items(
        session, variant_id=var_id, admin_id=admin_id, items=items
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Залито: <b>{batch.items_count}</b> аккаунтов\nПартия #{batch.id}",
        parse_mode="HTML",
    )
    await callback.answer()

    # уведомить подписчиков
    bot = callback.bot
    if bot is not None:
        await _notify_subscribers(bot, session, var_id)


async def _notify_subscribers(bot, session: AsyncSession, variant_id: int) -> None:
    from datetime import datetime

    from sqlalchemy import select

    res = await session.execute(
        select(StockSubscription).where(
            StockSubscription.variant_id == variant_id, StockSubscription.notified_at.is_(None)
        )
    )
    subs = list(res.scalars().all())
    if not subs:
        return
    v = await catalog_service.get_variant(session, variant_id)
    if v is None:
        return
    prod = await catalog_service.get_product(session, v.product_id)
    from src.bot.texts import STOCK_NEW_NOTIFY

    text = STOCK_NEW_NOTIFY.format(product=prod.name if prod else "", variant=v.name)
    sent = 0
    for s in subs:
        try:
            await bot.send_message(s.user_id, text, parse_mode="HTML")
            s.notified_at = datetime.now(UTC)
            sent += 1
        except Exception:
            continue
        await asyncio.sleep(0.04)
    await session.flush()
    await notify_admin(bot, f"🔔 Уведомлено {sent} подписчиков о пополнении стока «{v.name}»")


# ───────────────────── Просмотр стока ─────────────────────
@router.callback_query(F.data == "adm:stock")
async def cb_stock_root(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session, only_active=False)
    rows = [[InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"adm:stkcat:{c.id}")] for c in cats]
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    await callback.message.edit_text(
        "📦 <b>Сток</b>\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:stkcat:"))
async def cb_stock_cat(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[2])
    prods = await catalog_service.list_products(session, cat_id, only_active=False)
    rows = [[InlineKeyboardButton(text=f"🛒 {p.name}", callback_data=f"adm:stkprod:{p.id}")] for p in prods]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:stock")])
    await callback.message.edit_text(
        "📦 Выбери товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:stkprod:"))
async def cb_stock_prod(callback: CallbackQuery, session: AsyncSession) -> None:
    pid = int(callback.data.split(":")[2])
    variants = await catalog_service.list_variants(session, pid, only_active=False)
    counts = await catalog_service.stock_counts_for_variants(session, [v.id for v in variants])
    rows = [
        [
            InlineKeyboardButton(
                text=f"🎚 {v.name} • {counts.get(v.id, 0)} шт.",
                callback_data=f"adm:stock:var:{v.id}",
            )
        ]
        for v in variants
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="adm:stock")])
    await callback.message.edit_text(
        "📦 Выбери вариант:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:stock:var:"))
async def cb_stock_var(callback: CallbackQuery, session: AsyncSession) -> None:
    vid = int(callback.data.split(":")[3])
    v = await catalog_service.get_variant(session, vid)
    if v is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    count = await catalog_service.stock_count(session, vid)
    batches = await stock_service.list_batches(session, vid, limit=10)
    text = f"📦 <b>{v.name}</b>\nВ наличии: <b>{count}</b> шт.\n\nПоследние партии:"
    rows: list[list[InlineKeyboardButton]] = []
    for b in batches:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{b.id} • {b.items_count} шт. • {b.created_at:%Y-%m-%d %H:%M}",
                    callback_data=f"adm:stock:batch:{b.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="📥 Залить ещё", callback_data=f"adm:upload:var:{vid}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"adm:stkprod:{v.product_id}")])
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:stock:batch:"))
async def cb_stock_batch(callback: CallbackQuery, session: AsyncSession) -> None:
    bid = int(callback.data.split(":")[3])
    rows = [
        [
            InlineKeyboardButton(
                text="🗑 Удалить непроданные из партии",
                callback_data=f"adm:stock:batchdel:{bid}",
            )
        ],
        [InlineKeyboardButton(text="← Назад", callback_data="adm:stock")],
    ]
    await callback.message.edit_text(
        f"Партия #{bid}\n\nМожно удалить только непроданные позиции из этой партии.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:stock:batchdel:"))
async def cb_stock_batch_del(callback: CallbackQuery, session: AsyncSession) -> None:
    bid = int(callback.data.split(":")[3])
    removed = await stock_service.delete_batch(session, bid)
    await callback.answer(f"Удалено {removed}", show_alert=True)
    await callback.message.edit_text(f"Партия #{bid}: удалено непроданных {removed}.")
