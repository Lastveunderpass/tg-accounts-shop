from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ReferralEvent, User
from src.utils.refcode import encode_user_id


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    referrer_id: int | None = None,
) -> tuple[User, bool]:
    """Возвращает (user, created)."""
    res = await session.execute(select(User).where(User.id == telegram_id))
    user = res.scalar_one_or_none()
    if user is not None:
        changed = False
        if user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name is not None and user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if changed:
            await session.flush()
        return user, False

    if referrer_id == telegram_id:
        referrer_id = None
    if referrer_id is not None:
        ref_res = await session.execute(select(User.id).where(User.id == referrer_id))
        if ref_res.scalar_one_or_none() is None:
            referrer_id = None

    user = User(
        id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        balance_rub=Decimal("0"),
        total_spent_rub=Decimal("0"),
        ref_earned_rub=Decimal("0"),
        ref_code=encode_user_id(telegram_id),
        referrer_id=referrer_id,
        is_banned=False,
    )
    session.add(user)
    await session.flush()
    return user, True


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    res = await session.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    u = username.lstrip("@").lower()
    res = await session.execute(select(User).where(func.lower(User.username) == u))
    return res.scalar_one_or_none()


async def adjust_balance(session: AsyncSession, user_id: int, delta_rub: Decimal) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise ValueError(f"Пользователь {user_id} не найден")
    user.balance_rub = (user.balance_rub or Decimal("0")) + delta_rub
    await session.flush()
    return user


async def set_banned(session: AsyncSession, user_id: int, banned: bool) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise ValueError(f"Пользователь {user_id} не найден")
    user.is_banned = banned
    await session.flush()
    return user


async def referrals_count(session: AsyncSession, user_id: int) -> int:
    res = await session.execute(select(func.count(User.id)).where(User.referrer_id == user_id))
    return int(res.scalar() or 0)


async def referrals_earned(session: AsyncSession, user_id: int) -> Decimal:
    res = await session.execute(
        select(func.coalesce(func.sum(ReferralEvent.amount_rub), 0)).where(
            ReferralEvent.referrer_id == user_id
        )
    )
    return Decimal(res.scalar() or 0)
