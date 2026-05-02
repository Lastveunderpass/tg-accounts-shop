from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Setting


async def get_setting(session: AsyncSession, key: str, default: str | None = None) -> str | None:
    res = await session.execute(select(Setting.value).where(Setting.key == key))
    row = res.first()
    if row is None:
        return default
    return row[0]


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    res = await session.execute(select(Setting).where(Setting.key == key))
    existing = res.scalar_one_or_none()
    if existing is None:
        session.add(Setting(key=key, value=value))
    else:
        existing.value = value


async def get_int(session: AsyncSession, key: str, default: int) -> int:
    val = await get_setting(session, key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


async def get_decimal(session: AsyncSession, key: str, default: Decimal) -> Decimal:
    val = await get_setting(session, key)
    if val is None:
        return default
    try:
        return Decimal(val)
    except Exception:
        return default


async def get_bool(session: AsyncSession, key: str, default: bool) -> bool:
    val = await get_setting(session, key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "y")


async def all_settings(session: AsyncSession) -> dict[str, str]:
    res = await session.execute(select(Setting.key, Setting.value))
    return dict(res.all())
