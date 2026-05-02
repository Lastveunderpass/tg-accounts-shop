from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot import keyboards
from src.bot.handlers.admin._filters import AdminFilter
from src.bot.states import AdminWelcomeStates
from src.db.seed import DEFAULT_WELCOME_TEXT
from src.services import settings_service

router = Router(name="admin_welcome")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


def _kb_welcome(has_image: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="adm:welcome:text")],
        [InlineKeyboardButton(text="🖼 Загрузить картинку", callback_data="adm:welcome:img")],
    ]
    if has_image:
        rows.append(
            [InlineKeyboardButton(text="🗑 Убрать картинку", callback_data="adm:welcome:imgdel")]
        )
    rows.append(
        [InlineKeyboardButton(text="↩️ Сбросить текст", callback_data="adm:welcome:reset")]
    )
    rows.append([InlineKeyboardButton(text="← В меню", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_welcome(callback: CallbackQuery, session: AsyncSession) -> None:
    text = await settings_service.get_setting(session, "welcome_text", "")
    image = await settings_service.get_setting(session, "welcome_image_file_id", "")
    preview = text or "(пусто — будет использован дефолтный текст)"
    body = (
        "👋 <b>Приветствие</b>\n\n"
        "Это сообщение видит юзер при первом /start.\n\n"
        f"<b>Текст сейчас:</b>\n{preview}"
    )
    kb = _kb_welcome(bool(image))
    if image:
        try:
            await callback.message.answer_photo(image, caption=body, parse_mode="HTML", reply_markup=kb)
            await callback.answer()
            return
        except Exception:
            pass
    try:
        await callback.message.edit_text(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(body, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm:welcome")
async def cb_welcome_root(callback: CallbackQuery, session: AsyncSession) -> None:
    await _show_welcome(callback, session)


@router.callback_query(F.data == "adm:welcome:text")
async def cb_welcome_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminWelcomeStates.waiting_text)
    await callback.message.answer(
        "Пришли новый текст приветствия (поддерживается HTML).",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(AdminWelcomeStates.waiting_text)
async def msg_welcome_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    text = (message.html_text or message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым.")
        return
    await settings_service.set_setting(session, "welcome_text", text)
    await state.clear()
    await message.answer("✅ Текст приветствия обновлён.")


@router.callback_query(F.data == "adm:welcome:reset")
async def cb_welcome_reset(callback: CallbackQuery, session: AsyncSession) -> None:
    await settings_service.set_setting(session, "welcome_text", DEFAULT_WELCOME_TEXT)
    await callback.answer("Сброшено")
    await _show_welcome(callback, session)


@router.callback_query(F.data == "adm:welcome:img")
async def cb_welcome_img(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminWelcomeStates.waiting_image)
    await callback.message.answer(
        "Пришли картинку приветствия одним фото-сообщением.",
        reply_markup=keyboards.cancel_inline(),
    )
    await callback.answer()


@router.message(AdminWelcomeStates.waiting_image, F.photo)
async def msg_welcome_image(message: Message, state: FSMContext, session: AsyncSession) -> None:
    file_id = message.photo[-1].file_id
    await settings_service.set_setting(session, "welcome_image_file_id", file_id)
    await state.clear()
    await message.answer("✅ Картинка приветствия обновлена.")


@router.message(AdminWelcomeStates.waiting_image)
async def msg_welcome_image_invalid(message: Message) -> None:
    await message.answer("Нужно прислать именно фото (не файл).")


@router.callback_query(F.data == "adm:welcome:imgdel")
async def cb_welcome_img_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    await settings_service.set_setting(session, "welcome_image_file_id", "")
    await callback.answer("Картинка удалена")
    await _show_welcome(callback, session)
