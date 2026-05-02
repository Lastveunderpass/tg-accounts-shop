from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TopupStates(StatesGroup):
    waiting_amount = State()
    waiting_provider = State()
    waiting_asset = State()


class PromoStates(StatesGroup):
    waiting_code = State()


class PurchaseStates(StatesGroup):
    waiting_qty = State()
    waiting_promo = State()
    confirming = State()


# ─────────────────── Admin ───────────────────
class AdminCategoryStates(StatesGroup):
    waiting_name = State()
    waiting_rename = State()


class AdminProductStates(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_rename = State()
    waiting_image = State()


class AdminVariantStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_rename = State()
    waiting_new_price = State()


class AdminStockStates(StatesGroup):
    waiting_upload = State()
    confirming = State()
    waiting_media_group = State()


class AdminUserStates(StatesGroup):
    waiting_query = State()
    waiting_balance_delta = State()


class AdminPromoStates(StatesGroup):
    waiting_code = State()
    waiting_type = State()
    waiting_value = State()
    waiting_options = State()


class AdminBroadcastStates(StatesGroup):
    waiting_text = State()
    confirming = State()


class AdminRefundStates(StatesGroup):
    waiting_choice = State()
    waiting_note = State()


class AdminSettingsStates(StatesGroup):
    waiting_value = State()


class AdminWelcomeStates(StatesGroup):
    waiting_text = State()
    waiting_image = State()
