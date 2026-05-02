from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import Setting

DEFAULT_SETTING_KEYS: dict[str, str] = {
    "referral_percent": "default_referral_percent",
    "min_topup_rub": "default_min_topup_rub",
    "stock_low_threshold": "default_stock_low_threshold",
    "max_qty_per_order": "default_max_qty_per_order",
    "notify_new_user": "default_notify_new_user",
    "notify_new_topup": "default_notify_new_topup",
    "notify_new_purchase": "default_notify_new_purchase",
    "notify_low_stock": "default_notify_low_stock",
    "notify_refund": "default_notify_refund",
    "debug_mode": "debug_mode",
}


def _default_value(name: str) -> str:
    settings = get_settings()
    val = getattr(settings, name)
    if isinstance(val, bool):
        return "1" if val else "0"
    return str(val)


async def seed_settings(session: AsyncSession) -> None:
    """Создаёт записи Setting с дефолтами из .env, не трогая уже существующие."""
    result = await session.execute(select(Setting.key))
    existing = {row[0] for row in result.all()}
    for key, attr in DEFAULT_SETTING_KEYS.items():
        if key in existing:
            continue
        session.add(Setting(key=key, value=_default_value(attr)))
    await session.flush()
