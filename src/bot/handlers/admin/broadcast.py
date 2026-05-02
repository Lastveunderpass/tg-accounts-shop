from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.handlers.admin._filters import AdminFilter
from src.bot.states import AdminBroadcastStates
from src.db.models import Broadcast, User

router = Router(name="admin_broadcast")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "adm:bcast")
async def cb_bcast_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcastStates.waiting_text)
    await callback.message.edit_text(
        "📣 Введи текст рассылки. Поддерживается HTML (<b>жирный</b>, <i>курсив</i>, <code>код</code>).",
        parse_mode="HTML",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_text)
async def msg_bcast_text(message: Message, state: FSMContext) -> None:
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("Текст не может быть пустым.")
        return
    await state.update_data(text=text)
    await state.set_state(AdminBroadcastStates.confirming)
    rows = [
        [
            InlineKeyboardButton(text="✅ Запустить", callback_data="adm:bcast:start"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ]
    ]
    await message.answer(
        f"Будет отправлено всем активным пользователям:\n\n{text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        disable_web_page_preview=True,
    )


@router.callback_query(AdminBroadcastStates.confirming, F.data == "adm:bcast:start")
async def cb_bcast_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    text = str(data["text"])
    await state.clear()

    res = await session.execute(select(User.id).where(User.is_banned.is_(False)))
    user_ids = [row[0] for row in res.all()]

    bc = Broadcast(
        admin_id=callback.from_user.id if callback.from_user else 0, text=text
    )
    session.add(bc)
    await session.flush()
    await session.commit()

    sent = 0
    failed = 0
    bot = callback.bot
    msg = await callback.message.answer(f"Рассылка запущена на {len(user_ids)} получателей...")
    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
        except Exception:
            failed += 1
        if i % 50 == 0:
            try:
                await msg.edit_text(f"⏳ {i}/{len(user_ids)} (✓{sent} ✗{failed})")
            except Exception:
                pass
        await asyncio.sleep(0.04)

    bc.sent_count = sent
    bc.failed_count = failed
    bc.finished_at = datetime.now(UTC)
    await session.flush()
    await callback.message.answer(
        f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}"
    )
    await callback.answer()
