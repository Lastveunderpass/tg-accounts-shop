from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select

from src.db.models import Topup, TopupStatus, User
from src.db.session import session_scope
from src.logger import get_logger
from src.services import referral_service
from src.services.notifications import notify_admin
from src.utils.money import fmt_rub, quantize_rub

logger = get_logger("payments")


async def process_paid_invoice(bot: Bot, *, invoice_id: int) -> bool:
    """Обрабатывает оплату Topup. Идемпотентно: повторный вызов = no-op."""
    async with session_scope() as session:
        res = await session.execute(
            select(Topup).where(Topup.cryptobot_invoice_id == invoice_id)
        )
        topup = res.scalar_one_or_none()
        if topup is None:
            logger.warning("paid_invoice_unknown", invoice_id=invoice_id)
            return False
        if topup.status == TopupStatus.paid:
            return True

        user = await session.get(User, topup.user_id)
        if user is None:
            logger.warning("paid_invoice_no_user", invoice_id=invoice_id, user_id=topup.user_id)
            return False

        topup.status = TopupStatus.paid
        topup.paid_at = datetime.now(UTC)
        user.balance_rub = quantize_rub((user.balance_rub or 0) + topup.amount_rub)
        await session.flush()

        # реф. бонус
        ref_event = await referral_service.credit_referral_for_topup(
            session, topup=topup, referee=user
        )

    # уведомления — после коммита транзакции
    try:
        await bot.send_message(
            user.id,
            f"✅ Пополнение на <b>{fmt_rub(topup.amount_rub)}</b> зачислено. "
            f"Баланс: <b>{fmt_rub(user.balance_rub)}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("notify_user_paid_failed", user_id=user.id, error=str(e))

    await notify_admin(
        bot,
        f"💰 Пополнение #{topup.id} • <b>{fmt_rub(topup.amount_rub)}</b> "
        f"({topup.crypto_amount} {topup.crypto_asset.value}) от user <code>{user.id}</code>"
        + (f" @{user.username}" if user.username else ""),
        key="notify_new_topup",
    )

    if ref_event is not None:
        referrer, amount = ref_event
        try:
            await bot.send_message(
                referrer.id,
                f"💸 Реферальный бонус: <b>{fmt_rub(amount)}</b> зачислен на баланс.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    return True
