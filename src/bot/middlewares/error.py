from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.bot import texts
from src.logger import get_logger
from src.services.notifications import notify_admin_error

logger = get_logger("error")


class ErrorMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logger.exception("handler_error", error=str(e))
            try:
                if isinstance(event, Message):
                    await event.answer(texts.ERROR_GENERIC)
                elif isinstance(event, CallbackQuery):
                    await event.answer(texts.ERROR_GENERIC, show_alert=True)
            except TelegramAPIError:
                pass
            await notify_admin_error(self.bot, where=type(event).__name__, exc=e)
            return None
