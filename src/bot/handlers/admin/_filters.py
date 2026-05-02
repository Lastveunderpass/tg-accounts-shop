from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from src.config import get_settings


class AdminFilter(BaseFilter):
    async def __call__(self, event: Any) -> bool:
        admin_id = get_settings().admin_id
        if isinstance(event, Message) and event.from_user is not None:
            return event.from_user.id == admin_id
        if isinstance(event, CallbackQuery) and event.from_user is not None:
            return event.from_user.id == admin_id
        return False
