from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards, texts
from src.bot.states import TopupStates
from src.db.models import CryptoAsset, PaymentProvider, Topup, TopupStatus, User
from src.services import (
    crypto_service,
    lolzteam_service,
    settings_service,
)
from src.services.lolzteam_client import LolzteamError
from src.utils.money import fmt_crypto, fmt_rub, quantize_rub

router = Router(name="balance")


def _fmt_percent(p: Decimal) -> str:
    s = format(p.normalize(), "f") if p == p.to_integral() else format(p, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


async def _resolve_providers(session: AsyncSession) -> tuple[bool, bool, Decimal]:
    """Возвращает (cryptobot_on, lolzteam_on, lolzteam_surcharge_percent)."""
    from src.config import get_settings as _gs

    cfg = _gs()
    crypto_on = await settings_service.get_bool(session, "cryptobot_enabled", True)
    lolz_on_setting = await settings_service.get_bool(session, "lolzteam_enabled", False)
    lolz_on = lolz_on_setting and cfg.lolzteam_configured
    surcharge = await settings_service.get_decimal(
        session, "lolzteam_surcharge_percent", Decimal("6")
    )
    return crypto_on, lolz_on, surcharge


@router.message(F.text == texts.MENU_BALANCE)
async def menu_balance(message: Message, user: User, session: AsyncSession) -> None:
    rows = [[InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup_start")]]
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
    crypto_on, lolz_on, _ = await _resolve_providers(session)
    if not crypto_on and not lolz_on:
        await callback.answer(texts.TOPUP_PROVIDER_NONE, show_alert=True)
        return

    min_topup = await settings_service.get_int(session, "min_topup_rub", 100)
    await state.set_state(TopupStates.waiting_amount)
    await state.update_data(min_topup=min_topup)
    await callback.message.answer(
        texts.TOPUP_AMOUNT_PROMPT.format(min=min_topup),
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(TopupStates.waiting_amount)
async def msg_topup_amount(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
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

    crypto_on, lolz_on, surcharge = await _resolve_providers(session)
    if crypto_on and lolz_on:
        await state.set_state(TopupStates.waiting_provider)
        await message.answer(
            texts.TOPUP_PROVIDER_PROMPT,
            reply_markup=keyboards.topup_provider_keyboard(
                cryptobot_enabled=True,
                lolzteam_enabled=True,
                surcharge_percent=_fmt_percent(surcharge),
            ),
        )
    elif crypto_on:
        await state.set_state(TopupStates.waiting_asset)
        await message.answer(
            texts.TOPUP_ASSET_PROMPT, reply_markup=keyboards.crypto_assets_keyboard()
        )
    elif lolz_on:
        # сразу создаём Lolzteam-инвойс
        await _create_lolzteam_invoice(message, message.from_user.id, state, session, bot=bot)
    else:
        await message.answer(texts.TOPUP_PROVIDER_NONE)
        await state.clear()


@router.callback_query(TopupStates.waiting_provider, F.data.startswith("topup_provider:"))
async def cb_topup_provider(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    provider = callback.data.split(":", 1)[1]
    if provider == "cryptobot":
        await state.set_state(TopupStates.waiting_asset)
        await callback.message.answer(
            texts.TOPUP_ASSET_PROMPT, reply_markup=keyboards.crypto_assets_keyboard()
        )
        await callback.answer()
        return
    if provider == "lolzteam":
        await callback.message.edit_text("⏳ Создаю счёт...")
        await _create_lolzteam_invoice(callback.message, user.id, state, session, bot=bot)
        await callback.answer()
        return
    await callback.answer("Неизвестный способ оплаты", show_alert=True)


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


async def _create_lolzteam_invoice(
    message: Message,
    user_id: int,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot | None = None,
) -> None:
    data = await state.get_data()
    amount_rub = Decimal(data["amount_rub"])

    bot_username = ""
    if bot is not None:
        try:
            me = await bot.me()
            bot_username = me.username or ""
        except Exception:
            bot_username = ""

    try:
        topup = await lolzteam_service.create_topup_invoice(
            session,
            user_id=user_id,
            amount_rub=amount_rub,
            bot_username=bot_username,
        )
    except LolzteamError as e:
        await message.answer(f"❌ Не удалось создать счёт Lolzteam: {e}")
        await state.clear()
        return
    except Exception as e:
        await message.answer(f"❌ Не удалось создать счёт: {e}")
        await state.clear()
        return

    await state.clear()
    rows = [[InlineKeyboardButton(text="💳 Оплатить", url=topup.pay_url)]]
    surcharge_amount = (topup.gross_amount_rub or topup.amount_rub) - topup.amount_rub
    await message.answer(
        texts.TOPUP_LOLZTEAM_INVOICE_CREATED.format(
            amount_rub=fmt_rub(topup.amount_rub),
            percent=_fmt_percent(topup.surcharge_percent or Decimal("0")),
            surcharge=fmt_rub(surcharge_amount),
            gross=fmt_rub(topup.gross_amount_rub or topup.amount_rub),
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "topup_pending")
async def cb_topup_pending(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
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
        if t.provider == PaymentProvider.cryptobot and t.crypto_amount and t.crypto_asset:
            label = (
                f"#{t.id} • CryptoBot • {fmt_rub(t.amount_rub)} • "
                f"{fmt_crypto(t.crypto_amount, t.crypto_asset.value)}"
            )
        else:
            gross = t.gross_amount_rub or t.amount_rub
            label = f"#{t.id} • Lolzteam • {fmt_rub(t.amount_rub)} (к оплате {fmt_rub(gross)})"
        rows.append([InlineKeyboardButton(text=label, url=t.pay_url)])
    await callback.message.answer(
        texts.TOPUP_PENDING_LIST_HEADER,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()
