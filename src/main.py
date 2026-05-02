from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from src.bot.dispatcher import build_bot, build_dispatcher
from src.config import get_settings
from src.db.seed import seed_settings
from src.db.session import SessionLocal, engine
from src.logger import get_logger, setup_logging
from src.services.backup_service import run_sqlite_backup
from src.services.cryptobot_polling import CryptoBotPoller
from src.services.lolzteam_polling import LolzteamPoller
from src.services.notifications import notify_admin
from src.webhooks.cryptobot import build_router as cryptobot_router
from src.webhooks.lolzteam import build_router as lolzteam_router

setup_logging()
logger = get_logger("main")
settings = get_settings()


async def _seed() -> None:
    async with SessionLocal() as session:
        await seed_settings(session)
        await session.commit()


def _build_scheduler() -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone=settings.tz)
    sched.add_job(
        run_sqlite_backup,
        trigger=CronTrigger(hour=settings.backup_hour, minute=settings.backup_minute),
        id="daily_backup",
        replace_existing=True,
    )
    return sched


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _seed()

    bot = app.state.bot
    dp = app.state.dp

    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=None), name="aiogram-polling"
    )

    poller: CryptoBotPoller | None = None
    if settings.cryptobot_polling:
        poller = CryptoBotPoller(bot)
        await poller.start()
    app.state.poller = poller

    lolz_poller: LolzteamPoller | None = None
    if settings.lolzteam_polling and settings.lolzteam_configured:
        lolz_poller = LolzteamPoller(bot)
        await lolz_poller.start()
    app.state.lolz_poller = lolz_poller

    scheduler = _build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler

    try:
        await notify_admin(bot, "🟢 Бот запущен.")
    except Exception:
        pass

    try:
        yield
    finally:
        try:
            await notify_admin(bot, "🔴 Бот останавливается.")
        except Exception:
            pass
        if poller is not None:
            await poller.stop()
        if lolz_poller is not None:
            await lolz_poller.stop()
        scheduler.shutdown(wait=False)
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
        await bot.session.close()
        await engine.dispose()


def build_app() -> FastAPI:
    app = FastAPI(title="tg-accounts-shop", lifespan=lifespan)

    bot = build_bot()
    dp = build_dispatcher(bot)
    app.state.bot = bot
    app.state.dp = dp

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if not settings.cryptobot_polling:
        app.include_router(cryptobot_router(bot))
    else:
        logger.info("cryptobot_polling_mode")

    # Lolzteam webhook регистрируем всегда, если настроен — даже в polling-режиме
    # это даёт мгновенный кредит при оплате (polling — лишь подстраховка).
    if settings.lolzteam_configured:
        app.include_router(lolzteam_router(bot))

    return app


app = build_app()


def main() -> None:
    # Передаём готовый app, а не строку "src.main:app", чтобы избежать
    # двойного импорта модуля (при `python -m src.main` модуль исполняется
    # под именем __main__, а uvicorn по строке импортирует его ещё раз
    # как src.main — что приводило к двойной регистрации aiogram-роутеров).
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
