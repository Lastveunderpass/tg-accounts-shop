from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select

from src.db.models import PaymentProvider, Topup, TopupStatus, User
from src.db.session import session_scope
from src.logger import get_logger
from src.services import referral_service
from src.services.notifications import notify_admin
from src.utils.money import fmt_rub, quantize_rub

logger = get_logger("payments")


async def _process_by_predicate(bot: Bot, where_clause) -> bool:  # type: ignore[no-untyped-def]
    async with session_scope() as session:
        res = await session.execute(select(Topup).where(where_clause))
        topup = res.scalar_one_or_none()
        if topup is None:
            return False
        if topup.status == TopupStatus.paid:
            return True
        user = await session.get(User, topup.user_id)
        if user is None:
            logger.warning("paid_topup_no_user", topup_id=topup.id, user_id=topup.user_id)
            return False

        topup.status = TopupStatus.paid
        topup.paid_at = datetime.now(UTC)
        user.balance_rub = quantize_rub((user.balance_rub or 0) + topup.amount_rub)
        await session.flush()

        ref_event = await referral_service.credit_referral_for_topup(
            session, topup=topup, referee=user
        )

        topup_id = topup.id
        topup_amount = topup.amount_rub
        provider = topup.provider
        crypto_amount = topup.crypto_amount
        crypto_asset = topup.crypto_asset
        gross = topup.gross_amount_rub
        user_balance = user.balance_rub
        user_id = user.id
        user_username = user.username
        ref_payload = (ref_event[0].id, ref_event[1]) if ref_event else None

    # уведомления — после коммита транзакции
    try:
        await bot.send_message(
            user_id,
            f"✅ Пополнение на <b>{fmt_rub(topup_amount)}</b> зачислено. "
            f"Баланс: <b>{fmt_rub(user_balance)}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("notify_user_paid_failed", user_id=user_id, error=str(e))

    if provider == PaymentProvider.cryptobot:
        details = (
            f"({crypto_amount} {crypto_asset.value if crypto_asset else ''})"
            if crypto_amount is not None
            else ""
        )
        provider_label = "CryptoBot"
    else:
        details = f"(оплачено {fmt_rub(gross)})" if gross is not None else ""
        provider_label = "Lolzteam"

    await notify_admin(
        bot,
        f"💰 Пополнение #{topup_id} • {provider_label} • <b>{fmt_rub(topup_amount)}</b> "
        f"{details} от user <code>{user_id}</code>"
        + (f" @{user_username}" if user_username else ""),
        key="notify_new_topup",
    )

    if ref_payload is not None:
        ref_user_id, ref_amount = ref_payload
        try:
            await bot.send_message(
                ref_user_id,
                f"💸 Реферальный бонус: <b>{fmt_rub(ref_amount)}</b> зачислен на баланс.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    return True


async def process_paid_invoice(bot: Bot, *, invoice_id: int) -> bool:
    """Обработка оплаты CryptoBot. Идемпотентно: повторный вызов = no-op."""
    return await _process_by_predicate(
        bot, Topup.cryptobot_invoice_id == invoice_id
    )


async def process_paid_lolzteam(
    bot: Bot, *, invoice_id: int | None = None, payment_id: str | None = None
) -> bool:
    """Обработка оплаты Lolzteam. Идемпотентно."""
    if invoice_id is None and payment_id is None:
        return False
    where = (
        Topup.lolzteam_invoice_id == invoice_id
        if invoice_id is not None
        else Topup.lolzteam_payment_id == payment_id
    )
    return await _process_by_predicate(bot, where)
