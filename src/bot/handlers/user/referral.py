from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import texts
from src.db.models import User
from src.services import settings_service, users_service
from src.utils.money import fmt_rub

router = Router(name="referral")


@router.message(F.text == texts.MENU_REFERRAL)
async def menu_referral(message: Message, user: User, session: AsyncSession) -> None:
    bot = message.bot
    me = await bot.get_me() if bot is not None else None
    bot_username = me.username if me is not None else "your_bot"
    link = f"https://t.me/{bot_username}?start=ref_{user.ref_code}"

    percent = await settings_service.get_int(session, "referral_percent", 5)
    count = await users_service.referrals_count(session, user.id)
    earned = user.ref_earned_rub or await users_service.referrals_earned(session, user.id)

    await message.answer(
        texts.REFERRAL_INFO.format(
            percent=percent,
            link=link,
            count=count,
            earned=fmt_rub(earned),
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
