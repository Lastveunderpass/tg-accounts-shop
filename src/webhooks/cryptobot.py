from __future__ import annotations

import hashlib
import hmac
from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Header, HTTPException, Request

from src.config import get_settings
from src.logger import get_logger
from src.services.payment_processor import process_paid_invoice

logger = get_logger("cryptobot.webhook")


def build_router(bot: Bot) -> APIRouter:
    router = APIRouter()
    settings = get_settings()

    @router.post("/cryptobot/webhook")
    async def cryptobot_webhook(
        request: Request,
        crypto_pay_api_signature: str = Header(default="", alias="crypto-pay-api-signature"),
    ) -> dict[str, Any]:
        body = await request.body()
        # подпись вычисляется как HMAC-SHA256(sha256(api_token), body)
        token_hash = hashlib.sha256(settings.cryptobot_token.encode("utf-8")).digest()
        expected = hmac.new(token_hash, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, crypto_pay_api_signature):
            logger.warning("cryptobot_webhook_bad_signature")
            raise HTTPException(status_code=401, detail="bad signature")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="bad json") from None

        update_type = (payload or {}).get("update_type", "")
        invoice = (payload or {}).get("payload") or {}
        if update_type == "invoice_paid":
            invoice_id = int(invoice.get("invoice_id") or 0)
            if invoice_id:
                await process_paid_invoice(bot, invoice_id=invoice_id)
        return {"ok": True}

    return router
