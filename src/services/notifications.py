from __future__ import annotations

import asyncio
import traceback
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from src.config import get_settings
from src.db.session import session_scope
from src.logger import get_logger
from src.services import settings_service

logger = get_logger("notifications")


async def _enabled(key: str, default: bool = True) -> bool:
    async with session_scope() as session:
        return await settings_service.get_bool(session, key, default)


async def notify_admin(bot: Bot, text: str, *, key: str | None = None) -> None:
    """Отправляет сообщение админу. Если `key` передан — управляется флагом из Setting."""
    settings = get_settings()
    if key is not None:
        try:
            if not await _enabled(key, True):
                return
        except Exception as e:
            logger.warning("notify_flag_check_failed", error=str(e))
    try:
        await bot.send_message(settings.admin_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramAPIError as e:
        logger.warning("notify_admin_failed", error=str(e))


async def notify_admin_error(bot: Bot, where: str, exc: BaseException, extra: dict[str, Any] | None = None) -> None:
    settings = get_settings()
    if not settings.debug_mode:
        return
    try:
        async with session_scope() as session:
            debug = await settings_service.get_bool(session, "debug_mode", settings.debug_mode)
        if not debug:
            return
    except Exception:
        debug = settings.debug_mode
        if not debug:
            return
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    extra_str = ""
    if extra:
        extra_str = "\n".join(f"<b>{k}</b>: <code>{v}</code>" for k, v in extra.items())
    text = (
        f"🚨 <b>Ошибка</b> в <code>{where}</code>\n"
        f"<code>{type(exc).__name__}: {exc}</code>\n\n"
        f"{extra_str}\n"
        f"<pre>{tb[-3500:]}</pre>"
    )
    try:
        await bot.send_message(settings.admin_id, text, parse_mode="HTML", disable_web_page_preview=True)
    except TelegramAPIError as e:
        logger.warning("notify_admin_error_failed", error=str(e))


async def broadcast_to_users(
    bot: Bot, user_ids: list[int], text: str, *, sleep_between: float = 0.04
) -> tuple[int, int]:
    """Отправляет сообщение списку юзеров. Возвращает (sent, failed)."""
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
        except TelegramAPIError as e:
            failed += 1
            logger.debug("broadcast_send_failed", user_id=uid, error=str(e))
        await asyncio.sleep(sleep_between)
    return sent, failed
