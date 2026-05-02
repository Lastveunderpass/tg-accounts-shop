from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import texts
from src.services import users_service


def _extract_tg_user(event: TelegramObject) -> TgUser | None:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    # Update-обёртка от dp.update.outer_middleware — достаём пользователя из
    # содержимого апдейта (message / callback_query / chat_member и т.п.).
    for attr in ("message", "edited_message", "channel_post", "callback_query"):
        sub = getattr(event, attr, None)
        if sub is not None and getattr(sub, "from_user", None) is not None:
            return sub.from_user
    return getattr(event, "from_user", None)


def _extract_start_payload(event: TelegramObject) -> str | None:
    msg = event if isinstance(event, Message) else getattr(event, "message", None)
    if msg is not None and msg.text and msg.text.startswith("/start"):
        parts = msg.text.split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip()
    return None


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = _extract_tg_user(event)
        session: AsyncSession | None = data.get("session")
        if tg_user is None or session is None or tg_user.is_bot:
            return await handler(event, data)

        payload = _extract_start_payload(event)
        referrer_id: int | None = None
        if payload and payload.startswith("ref_"):
            ref_code = payload[4:]
            from sqlalchemy import select

            from src.db.models import User

            res = await session.execute(select(User).where(User.ref_code == ref_code))
            ref = res.scalar_one_or_none()
            if ref is not None and ref.id != tg_user.id:
                referrer_id = ref.id

        user, _ = await users_service.get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            referrer_id=referrer_id,
        )
        data["user"] = user

        if user.is_banned:
            msg = event if isinstance(event, Message) else getattr(event, "message", None)
            cb = event if isinstance(event, CallbackQuery) else getattr(event, "callback_query", None)
            if isinstance(msg, Message):
                await msg.answer(texts.BANNED)
            elif isinstance(cb, CallbackQuery):
                await cb.answer(texts.BANNED, show_alert=True)
            return None

        return await handler(event, data)
