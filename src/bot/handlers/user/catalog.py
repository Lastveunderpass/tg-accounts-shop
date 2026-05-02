from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards, texts
from src.bot.states import PurchaseStates
from src.db.models import StockSubscription, User
from src.services import catalog_service, orders_service, settings_service
from src.services.notifications import notify_admin
from src.services.orders_service import OrderError
from src.utils.money import fmt_rub
from src.utils.parsers import build_zip_archive

router = Router(name="catalog")


# ─────────────────── Главный экран каталога ───────────────────
@router.message(F.text == texts.MENU_CATALOG)
async def show_catalog(message: Message, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session)
    if not cats:
        await message.answer(texts.CATALOG_EMPTY)
        return
    rows = [
        [InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"cat:{c.id}")]
        for c in cats
    ]
    await message.answer(
        texts.CATALOG_TITLE,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("cat:"))
async def cb_open_category(callback: CallbackQuery, session: AsyncSession) -> None:
    cat_id = int(callback.data.split(":")[1])
    cat = await catalog_service.get_category(session, cat_id)
    if cat is None or not cat.is_active:
        await callback.answer("Категория недоступна", show_alert=True)
        return
    products = await catalog_service.list_products(session, cat_id)
    if not products:
        await callback.message.edit_text(texts.CATEGORY_EMPTY)
        await callback.answer()
        return
    rows = [
        [InlineKeyboardButton(text=f"🛒 {p.name}", callback_data=f"prod:{p.id}")] for p in products
    ]
    rows.append([InlineKeyboardButton(text=texts.BACK, callback_data="catalog_root")])
    await callback.message.edit_text(
        f"📁 <b>{cat.name}</b>\n\nВыбери товар:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "catalog_root")
async def cb_catalog_root(callback: CallbackQuery, session: AsyncSession) -> None:
    cats = await catalog_service.list_categories(session)
    rows = [
        [InlineKeyboardButton(text=f"📁 {c.name}", callback_data=f"cat:{c.id}")] for c in cats
    ]
    await callback.message.edit_text(
        texts.CATALOG_TITLE,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prod:"))
async def cb_open_product(callback: CallbackQuery, session: AsyncSession) -> None:
    prod_id = int(callback.data.split(":")[1])
    prod = await catalog_service.get_product(session, prod_id)
    if prod is None or not prod.is_active:
        await callback.answer("Товар недоступен", show_alert=True)
        return
    variants = await catalog_service.list_variants(session, prod_id)
    if not variants:
        await callback.message.edit_text(texts.PRODUCT_NO_VARIANTS)
        await callback.answer()
        return
    counts = await catalog_service.stock_counts_for_variants(session, [v.id for v in variants])
    rows: list[list[InlineKeyboardButton]] = []
    for v in variants:
        avail = counts.get(v.id, 0)
        label = f"{v.name} — {fmt_rub(v.price_rub)} ({'в наличии: ' + str(avail) if avail > 0 else 'нет'})"
        if avail > 0:
            rows.append([InlineKeyboardButton(text=label, callback_data=f"var:{v.id}")])
        else:
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"varsub:{v.id}")]
            )
    rows.append([InlineKeyboardButton(text=texts.BACK, callback_data=f"cat:{prod.category_id}")])
    desc = f"\n\n{prod.description}" if prod.description else ""
    body = f"🛒 <b>{prod.name}</b>{desc}\n\nВыбери вариант:"
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if prod.image_file_id:
        # карточку с картинкой шлём отдельным сообщением — edit_text для photo не подходит
        try:
            await callback.message.answer_photo(
                prod.image_file_id, caption=body, parse_mode="HTML", reply_markup=kb
            )
            await callback.answer()
            return
        except Exception:
            # битый file_id — фолбэк на текстовое сообщение
            pass

    try:
        await callback.message.edit_text(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(body, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("varsub:"))
async def cb_subscribe_variant(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    var_id = int(callback.data.split(":")[1])
    res = await session.execute(
        select(StockSubscription).where(
            StockSubscription.user_id == user.id, StockSubscription.variant_id == var_id
        )
    )
    if res.scalar_one_or_none() is not None:
        await callback.answer(texts.STOCK_ALREADY_SUBSCRIBED, show_alert=True)
        return
    session.add(StockSubscription(user_id=user.id, variant_id=var_id))
    await session.flush()
    await callback.answer(texts.STOCK_SUBSCRIBED, show_alert=True)


# ─────────────────── Покупка варианта ───────────────────
@router.callback_query(F.data.startswith("var:"))
async def cb_open_variant(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    var_id = int(callback.data.split(":")[1])
    variant = await catalog_service.get_variant(session, var_id)
    if variant is None or not variant.is_active:
        await callback.answer("Вариант недоступен", show_alert=True)
        return
    avail = await catalog_service.stock_count(session, var_id)
    if avail <= 0:
        await callback.answer("Нет в наличии", show_alert=True)
        return

    max_per_order = await settings_service.get_int(session, "max_qty_per_order", 10)
    max_qty = min(avail, max_per_order)

    await state.set_state(PurchaseStates.waiting_qty)
    await state.update_data(variant_id=var_id, max_qty=max_qty)
    prod = await catalog_service.get_product(session, variant.product_id)
    desc = f"\n\nЦена за 1 шт.: <b>{fmt_rub(variant.price_rub)}</b>"
    await callback.message.answer(
        f"🛒 <b>{prod.name if prod else ''} / {variant.name}</b>{desc}\n\n"
        + texts.QTY_PROMPT.format(max=max_qty),
        parse_mode="HTML",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(PurchaseStates.waiting_qty)
async def msg_qty(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    max_qty = int(data.get("max_qty", 1))
    text = (message.text or "").strip()
    try:
        qty = int(text)
    except ValueError:
        await message.answer(texts.QTY_INVALID.format(max=max_qty))
        return
    if qty < 1 or qty > max_qty:
        await message.answer(texts.QTY_INVALID.format(max=max_qty))
        return
    var_id = int(data["variant_id"])
    variant = await catalog_service.get_variant(session, var_id)
    if variant is None:
        await state.clear()
        await message.answer(texts.ERROR_GENERIC)
        return
    prod = await catalog_service.get_product(session, variant.product_id)
    subtotal = variant.price_rub * Decimal(qty)

    await state.update_data(qty=qty)
    await state.set_state(PurchaseStates.confirming)

    rows = [
        [InlineKeyboardButton(text="🎟 Применить промокод", callback_data="purchase_promo")],
        [
            InlineKeyboardButton(text="✅ Купить", callback_data="purchase_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ],
    ]
    await message.answer(
        texts.PURCHASE_CONFIRM.format(
            product=prod.name if prod else "",
            variant=variant.name,
            qty=qty,
            unit=fmt_rub(variant.price_rub),
            discount=fmt_rub(0),
            total=fmt_rub(subtotal),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(PurchaseStates.confirming, F.data == "purchase_promo")
async def cb_purchase_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PurchaseStates.waiting_promo)
    await callback.message.answer(texts.PROMO_PROMPT, reply_markup=keyboards.cancel_inline())
    await callback.answer()


@router.message(PurchaseStates.waiting_promo)
async def msg_purchase_promo(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    code = (message.text or "").strip()
    data = await state.get_data()
    var_id = int(data["variant_id"])
    qty = int(data["qty"])
    variant = await catalog_service.get_variant(session, var_id)
    if variant is None:
        await state.clear()
        return
    from src.services import promo_service

    subtotal = variant.price_rub * Decimal(qty)
    try:
        promo, discount = await promo_service.validate_promo_for_purchase(
            session, code=code, user=user, variant=variant, subtotal_rub=subtotal, qty=qty
        )
    except promo_service.PromoError as e:
        await message.answer(texts.PROMO_INVALID.format(reason=str(e)))
        await state.set_state(PurchaseStates.confirming)
        return
    except InvalidOperation:
        await message.answer(texts.PROMO_INVALID.format(reason="Некорректный промокод"))
        await state.set_state(PurchaseStates.confirming)
        return

    await state.update_data(promo_code=promo.code, discount=str(discount))
    await state.set_state(PurchaseStates.confirming)

    prod = await catalog_service.get_product(session, variant.product_id)
    rows = [
        [
            InlineKeyboardButton(text="✅ Купить", callback_data="purchase_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ],
    ]
    await message.answer(
        texts.PURCHASE_CONFIRM.format(
            product=prod.name if prod else "",
            variant=variant.name,
            qty=qty,
            unit=fmt_rub(variant.price_rub),
            discount=fmt_rub(discount),
            total=fmt_rub(subtotal - discount),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(PurchaseStates.confirming, F.data == "purchase_confirm")
async def cb_purchase_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    data = await state.get_data()
    var_id = int(data["variant_id"])
    qty = int(data["qty"])
    promo_code = data.get("promo_code")

    variant = await catalog_service.get_variant(session, var_id)
    if variant is None:
        await callback.answer("Вариант недоступен", show_alert=True)
        await state.clear()
        return
    max_per_order = await settings_service.get_int(session, "max_qty_per_order", 10)

    try:
        result = await orders_service.create_purchase(
            session,
            user=user,
            variant=variant,
            qty=qty,
            promo_code=promo_code,
            max_qty_per_order=max_per_order,
        )
    except OrderError as e:
        await callback.message.answer(f"❌ {e}")
        await state.clear()
        await callback.answer()
        return

    await state.clear()

    # выдача файлов
    prod = await catalog_service.get_product(session, variant.product_id)
    base_name = _safe_filename(f"{prod.name if prod else 'item'}_{variant.name}")
    from src.db.models import ProductFormat

    file_ext = "json" if (prod is not None and prod.format == ProductFormat.cookies_json) else "txt"
    if qty == 1:
        si = result.items[0]
        fname = si.file_name or f"{base_name}_1.{file_ext}"
        await callback.message.answer_document(
            BufferedInputFile(si.payload.encode("utf-8"), filename=fname),
            caption=texts.PURCHASE_OK.format(
                order_id=result.order.id,
                total=fmt_rub(result.order.total_rub),
                balance=fmt_rub(user.balance_rub),
            ),
            parse_mode="HTML",
        )
    else:
        files = [
            (si.file_name or f"{base_name}_{i + 1}.{file_ext}", si.payload)
            for i, si in enumerate(result.items)
        ]
        zip_bytes = build_zip_archive(files)
        await callback.message.answer_document(
            BufferedInputFile(zip_bytes, filename=f"{base_name}.zip"),
            caption=texts.PURCHASE_OK.format(
                order_id=result.order.id,
                total=fmt_rub(result.order.total_rub),
                balance=fmt_rub(user.balance_rub),
            ),
            parse_mode="HTML",
        )

    # уведомление админу
    bot = callback.bot
    if bot is not None:
        from src.utils.money import fmt_rub as _fmt
        await notify_admin(
            bot,
            (
                f"🛒 <b>Новая покупка</b>\n"
                f"Юзер: <code>{user.id}</code>"
                + (f" @{user.username}" if user.username else "")
                + f"\nЗаказ: #{result.order.id}\n"
                f"Товар: {prod.name if prod else ''} / {variant.name}\n"
                f"Кол-во: {qty}\n"
                f"Сумма: {_fmt(result.order.total_rub)}"
            ),
            key="notify_new_purchase",
        )

    # проверка низкого стока
    avail_after = await catalog_service.stock_count(session, variant.id)
    threshold = await settings_service.get_int(session, "stock_low_threshold", 5)
    if avail_after <= threshold and bot is not None:
        await notify_admin(
            bot,
            f"⚠️ Низкий сток: {prod.name if prod else ''} / {variant.name} — осталось {avail_after}",
            key="notify_low_stock",
        )

    await callback.answer()


def _safe_filename(s: str) -> str:
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        else:
            out.append("_")
    cleaned = "".join(out).strip("_")
    return cleaned or "item"



