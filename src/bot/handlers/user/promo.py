from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards, texts
from src.bot.states import PromoStates
from src.db.models import User
from src.services import promo_service
from src.utils.money import fmt_rub

router = Router(name="promo")


@router.message(F.text == texts.MENU_PROMO)
async def menu_promo(message: Message, state: FSMContext) -> None:
    await state.set_state(PromoStates.waiting_code)
    await message.answer(texts.PROMO_PROMPT, reply_markup=keyboards.cancel_inline())


@router.message(PromoStates.waiting_code)
async def msg_promo_code(
    message: Message, state: FSMContext, session: AsyncSession, user: User
) -> None:
    code = (message.text or "").strip()
    await state.clear()
    try:
        _promo, amount = await promo_service.activate_balance_promo(
            session, code=code, user=user
        )
    except promo_service.PromoError as e:
        await message.answer(texts.PROMO_INVALID.format(reason=str(e)))
        return
    await message.answer(texts.PROMO_BALANCE_OK.format(amount=fmt_rub(amount)), parse_mode="HTML")
