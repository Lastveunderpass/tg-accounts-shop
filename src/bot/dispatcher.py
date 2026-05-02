from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers.admin import (
    broadcast,
    categories,
    orders,
    products,
    settings_panel,
    stats,
    stock,
    variants,
)
from src.bot.handlers.admin import (
    menu as admin_menu,
)
from src.bot.handlers.admin import (
    promo as admin_promo,
)
from src.bot.handlers.admin import (
    users as admin_users,
)
from src.bot.handlers.user import balance, catalog, history, promo, referral, start
from src.bot.middlewares.db import DbSessionMiddleware
from src.bot.middlewares.error import ErrorMiddleware
from src.bot.middlewares.user import UserContextMiddleware
from src.config import get_settings


def build_bot() -> Bot:
    settings = get_settings()
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=None))


def build_dispatcher(bot: Bot) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares (порядок важен: error -> db -> user)
    dp.update.outer_middleware(ErrorMiddleware(bot))
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())

    # admin (ставим раньше, иначе фильтр AdminFilter будет проверяться после, что ок,
    # но важно чтобы админ-меню не перекрывалось пользовательскими хэндлерами с тем же текстом)
    dp.include_router(admin_menu.router)
    dp.include_router(categories.router)
    dp.include_router(products.router)
    dp.include_router(variants.router)
    dp.include_router(stock.router)
    dp.include_router(admin_users.router)
    dp.include_router(orders.router)
    dp.include_router(admin_promo.router)
    dp.include_router(stats.router)
    dp.include_router(broadcast.router)
    dp.include_router(settings_panel.router)

    # user
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(balance.router)
    dp.include_router(history.router)
    dp.include_router(referral.router)
    dp.include_router(promo.router)

    return dp
