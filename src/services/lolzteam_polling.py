from __future__ import annotations

import asyncio

from aiogram import Bot

from src.config import get_settings
from src.db.session import session_scope
from src.logger import get_logger
from src.services import lolzteam_service
from src.services.lolzteam_client import LolzteamClient
from src.services.payment_processor import process_paid_lolzteam

logger = get_logger("lolzteam.polling")


class LolzteamPoller:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._settings = get_settings()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="lolzteam-poller")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except TimeoutError:
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        client = LolzteamClient()
        try:
            while not self._stopping.is_set():
                try:
                    await self._tick(client)
                except Exception as e:
                    logger.warning("poll_tick_failed", error=str(e))
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(),
                        timeout=self._settings.lolzteam_poll_interval,
                    )
                except TimeoutError:
                    pass
        finally:
            await client.close()

    async def _tick(self, client: LolzteamClient) -> None:
        async with session_scope() as session:
            pending = await lolzteam_service.find_pending_topups(session, limit=200)
        if not pending:
            return
        ids = [t.lolzteam_invoice_id for t in pending if t.lolzteam_invoice_id is not None]
        paid_ids = await lolzteam_service.fetch_paid_invoice_ids(
            client,
            merchant_id=self._settings.lolzteam_merchant_id,
            candidate_ids=ids,
        )
        for inv_id in paid_ids:
            await process_paid_lolzteam(self.bot, invoice_id=inv_id)
        if paid_ids:
            logger.info("poll_paid_processed", count=len(paid_ids))
