from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ReferralEvent, Topup, User
from src.services import settings_service
from src.utils.money import percent_of, quantize_rub


async def credit_referral_for_topup(
    session: AsyncSession, *, topup: Topup, referee: User
) -> tuple[User, Decimal] | None:
    """Если у `referee` есть реферер — начисляет ему % от пополнения. Возвращает (referrer, amount)."""
    if referee.referrer_id is None:
        return None
    referrer = await session.get(User, referee.referrer_id)
    if referrer is None:
        return None

    percent = await settings_service.get_int(session, "referral_percent", 5)
    if percent <= 0:
        return None

    amount = percent_of(topup.amount_rub, percent)
    if amount <= 0:
        return None

    referrer.balance_rub = quantize_rub((referrer.balance_rub or Decimal("0")) + amount)
    referrer.ref_earned_rub = quantize_rub(
        (referrer.ref_earned_rub or Decimal("0")) + amount
    )
    session.add(
        ReferralEvent(
            referrer_id=referrer.id,
            referee_id=referee.id,
            topup_id=topup.id,
            amount_rub=amount,
        )
    )
    await session.flush()
    return referrer, amount
