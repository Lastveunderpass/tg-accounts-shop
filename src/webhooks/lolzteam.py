"""Webhook-эндпоинт для callback'ов от Lolzteam Market.

Lolzteam подписывает payload опциональным секретом (HMAC-SHA256 от тела). Если
LOLZTEAM_CALLBACK_SECRET задан — проверяем подпись; иначе принимаем без неё.
В любом случае процессинг идемпотентен (`process_paid_lolzteam`).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Header, HTTPException, Request

from src.config import get_settings
from src.logger import get_logger
from src.services.payment_processor import process_paid_lolzteam

logger = get_logger("lolzteam.webhook")


def build_router(bot: Bot) -> APIRouter:
    router = APIRouter()
    settings = get_settings()

    @router.post("/lolzteam/webhook")
    async def lolzteam_webhook(
        request: Request,
        x_signature: str = Header(default="", alias="X-Signature"),
    ) -> dict[str, Any]:
        body = await request.body()
        if settings.lolzteam_callback_secret:
            expected = hmac.new(
                settings.lolzteam_callback_secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, (x_signature or "").lower()):
                logger.warning("lolzteam_webhook_bad_signature")
                raise HTTPException(status_code=401, detail="bad signature")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="bad json") from None

        if not isinstance(payload, dict):
            return {"ok": True}

        # Структура колбэка может быть либо плоской, либо вложенной в `invoice`/`data`.
        invoice = payload
        if isinstance(payload.get("invoice"), dict):
            invoice = payload["invoice"]
        elif isinstance(payload.get("data"), dict):
            invoice = payload["data"]

        status = str(invoice.get("status", "")).lower()
        if status not in ("paid", "success", "successful", "completed"):
            return {"ok": True}

        invoice_id = invoice.get("invoice_id") or invoice.get("id")
        payment_id = invoice.get("payment_id")
        if invoice_id is None and payment_id is None:
            return {"ok": True}

        await process_paid_lolzteam(
            bot,
            invoice_id=int(invoice_id) if invoice_id is not None else None,
            payment_id=str(payment_id) if payment_id is not None else None,
        )
        return {"ok": True}

    return router
