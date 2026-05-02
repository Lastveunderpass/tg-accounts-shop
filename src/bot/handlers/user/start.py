from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards, texts
from src.config import get_settings
from src.db.models import User
from src.services import settings_service

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    settings = get_settings()
    is_admin = user.id == settings.admin_id

    welcome_text = await settings_service.get_setting(session, "welcome_text", texts.WELCOME)
    if not welcome_text:
        welcome_text = texts.WELCOME
    welcome_image = await settings_service.get_setting(session, "welcome_image_file_id", "")

    kb = keyboards.main_menu(is_admin)
    if welcome_image:
        try:
            await message.answer_photo(
                welcome_image, caption=welcome_text, parse_mode="HTML", reply_markup=kb
            )
            return
        except Exception:
            # битый file_id или картинка удалена — фолбэк на текст
            pass
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        try:
            await callback.message.edit_text(texts.CANCELLED)
        except Exception:
            await callback.message.answer(texts.CANCELLED)
    await callback.answer()


@router.message(F.text.in_({"/cancel", "Отмена"}))
async def cmd_cancel(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    settings = get_settings()
    is_admin = user.id == settings.admin_id
    await message.answer(texts.CANCELLED, reply_markup=keyboards.main_menu(is_admin))


@router.message(F.text == texts.MENU_PROFILE)
async def menu_profile(message: Message, user: User, session: AsyncSession) -> None:
    from sqlalchemy import func, select

    from src.db.models import Order, OrderStatus

    res = await session.execute(
        select(func.count(Order.id)).where(
            Order.user_id == user.id, Order.status == OrderStatus.paid
        )
    )
    purchases = int(res.scalar() or 0)
    from src.utils.money import fmt_rub

    await message.answer(
        texts.PROFILE.format(
            id=user.id,
            balance=fmt_rub(user.balance_rub),
            spent=fmt_rub(user.total_spent_rub),
            purchases=purchases,
            ref_code=user.ref_code,
        ),
        parse_mode="HTML",
    )


@router.message(F.text == texts.MENU_SUPPORT)
async def menu_support(message: Message) -> None:
    settings = get_settings()
    await message.answer(
        texts.SUPPORT_TEXT,
        parse_mode="HTML",
        reply_markup=keyboards.support_keyboard(settings.support_url),
    )
