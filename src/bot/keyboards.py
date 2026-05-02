from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.bot import texts
from src.db.models import CryptoAsset


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=texts.MENU_CATALOG), KeyboardButton(text=texts.MENU_BALANCE)],
        [KeyboardButton(text=texts.MENU_PROFILE), KeyboardButton(text=texts.MENU_HISTORY)],
        [KeyboardButton(text=texts.MENU_REFERRAL), KeyboardButton(text=texts.MENU_PROMO)],
        [KeyboardButton(text=texts.MENU_SUPPORT)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=texts.MENU_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.CANCEL, callback_data="cancel")]]
    )


def crypto_assets_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="USDT", callback_data="topup_asset:USDT"),
            InlineKeyboardButton(text="TON", callback_data="topup_asset:TON"),
        ],
        [
            InlineKeyboardButton(text="BTC", callback_data="topup_asset:BTC"),
            InlineKeyboardButton(text="LTC", callback_data="topup_asset:LTC"),
        ],
        [InlineKeyboardButton(text=texts.CANCEL, callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_keyboard(support_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📨 Написать в поддержку", url=support_url)]]
    )


def confirm_inline(callback_yes: str, callback_no: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=callback_yes),
                InlineKeyboardButton(text="❌ Отмена", callback_data=callback_no),
            ]
        ]
    )


# Список всех криптоактивов в боте
ALL_ASSETS = [a.value for a in CryptoAsset]
