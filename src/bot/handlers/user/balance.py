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

from src.bot import keyboards, texts
from src.bot.states import TopupStates
from src.db.models import CryptoAsset, TopupStatus, User
from src.services import crypto_service, settings_service
from src.utils.money import fmt_crypto, fmt_rub, quantize_rub

router = Router(name="balance")


@router.message(F.text == texts.MENU_BALANCE)
async def menu_balance(message: Message, user: User, session: AsyncSession) -> None:
    rows = [[InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup_start")]]
    # активные счета
    from sqlalchemy import select

    from src.db.models import Topup

    res = await session.execute(
        select(Topup)
        .where(Topup.user_id == user.id, Topup.status == TopupStatus.pending)
        .order_by(Topup.id.desc())
        .limit(5)
    )
    pending = list(res.scalars().all())
    if pending:
        rows.append(
            [InlineKeyboardButton(text=f"⏳ Активные счета ({len(pending)})", callback_data="topup_pending")]
        )

    await message.answer(
        texts.BALANCE_VIEW.format(
            balance=fmt_rub(user.balance_rub),
            spent=fmt_rub(user.total_spent_rub),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "topup_start")
async def cb_topup_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    min_topup = await settings_service.get_int(session, "min_topup_rub", 100)
    await state.set_state(TopupStates.waiting_amount)
    await state.update_data(min_topup=min_topup)
    await callback.message.answer(
        texts.TOPUP_AMOUNT_PROMPT.format(min=min_topup),
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(TopupStates.waiting_amount)
async def msg_topup_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    min_topup = int(data.get("min_topup", 100))
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = quantize_rub(Decimal(text))
    except (InvalidOperation, ValueError):
        await message.answer(texts.TOPUP_AMOUNT_INVALID.format(min=min_topup))
        return
    if amount < Decimal(min_topup):
        await message.answer(texts.TOPUP_AMOUNT_INVALID.format(min=min_topup))
        return
    await state.update_data(amount_rub=str(amount))
    await state.set_state(TopupStates.waiting_asset)
    await message.answer(
        texts.TOPUP_ASSET_PROMPT, reply_markup=keyboards.crypto_assets_keyboard()
    )


@router.callback_query(TopupStates.waiting_asset, F.data.startswith("topup_asset:"))
async def cb_topup_asset(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    asset_str = callback.data.split(":")[1]
    try:
        asset = CryptoAsset(asset_str)
    except ValueError:
        await callback.answer("Неизвестный актив", show_alert=True)
        return
    data = await state.get_data()
    amount_rub = Decimal(data["amount_rub"])

    await callback.message.edit_text("⏳ Создаю счёт...")

    try:
        topup = await crypto_service.create_topup_invoice(
            session, user_id=user.id, amount_rub=amount_rub, asset=asset
        )
    except Exception as e:
        await callback.message.answer(f"❌ Не удалось создать счёт: {e}")
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    rows = [[InlineKeyboardButton(text="💳 Оплатить", url=topup.pay_url)]]
    await callback.message.answer(
        texts.TOPUP_INVOICE_CREATED.format(
            amount_rub=fmt_rub(topup.amount_rub),
            amount_crypto=fmt_crypto(topup.crypto_amount, asset.value),
            asset=asset.value,
            rate=fmt_rub(topup.crypto_rate_rub),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "topup_pending")
async def cb_topup_pending(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    from sqlalchemy import select

    from src.db.models import Topup

    res = await session.execute(
        select(Topup)
        .where(Topup.user_id == user.id, Topup.status == TopupStatus.pending)
        .order_by(Topup.id.desc())
        .limit(10)
    )
    pending = list(res.scalars().all())
    if not pending:
        await callback.answer(texts.TOPUP_NO_PENDING, show_alert=True)
        return
    rows = []
    for t in pending:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{t.id} • {fmt_rub(t.amount_rub)} • {fmt_crypto(t.crypto_amount, t.crypto_asset.value)}",
                    url=t.pay_url,
                )
            ]
        )
    await callback.message.answer(
        texts.TOPUP_PENDING_LIST_HEADER,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()
