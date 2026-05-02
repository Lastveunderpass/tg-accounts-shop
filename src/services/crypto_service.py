from __future__ import annotations

from decimal import Decimal

from aiocryptopay import AioCryptoPay, Networks
from aiocryptopay.models.invoice import Invoice
from aiocryptopay.models.update import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import CryptoAsset, Topup, TopupStatus
from src.logger import get_logger
from src.utils.money import crypto_charge_amount

_settings = get_settings()
logger = get_logger("crypto")


def build_client() -> AioCryptoPay:
    network = Networks.TEST_NET if _settings.cryptobot_testnet else Networks.MAIN_NET
    return AioCryptoPay(token=_settings.cryptobot_token, network=network)


async def get_rate_rub_per_crypto(client: AioCryptoPay, asset: CryptoAsset) -> Decimal:
    """Сколько рублей стоит 1 единица криптоактива (по курсу CryptoBot)."""
    rates = await client.get_exchange_rates()
    for r in rates:
        if r.source == asset.value and r.target == "RUB" and getattr(r, "is_valid", True):
            return Decimal(str(r.rate))
    raise RuntimeError(f"Курс {asset.value}->RUB не найден в CryptoBot")


async def create_topup_invoice(
    session: AsyncSession,
    *,
    user_id: int,
    amount_rub: Decimal,
    asset: CryptoAsset,
    client: AioCryptoPay | None = None,
) -> Topup:
    """Создаёт инвойс CryptoBot и Topup-запись."""
    own_client = client is None
    if client is None:
        client = build_client()
    try:
        rate = await get_rate_rub_per_crypto(client, asset)
        crypto_amount = crypto_charge_amount(amount_rub, rate, asset.value)

        invoice: Invoice = await client.create_invoice(
            asset=asset.value,
            amount=float(crypto_amount),
            description=f"Пополнение баланса на {amount_rub} ₽",
            payload=f"topup:{user_id}",
            expires_in=1800,
        )

        topup = Topup(
            user_id=user_id,
            amount_rub=amount_rub,
            crypto_asset=asset,
            crypto_amount=crypto_amount,
            crypto_rate_rub=rate,
            cryptobot_invoice_id=int(invoice.invoice_id),
            pay_url=invoice.bot_invoice_url or invoice.mini_app_invoice_url or invoice.web_app_invoice_url or "",
            status=TopupStatus.pending,
        )
        session.add(topup)
        await session.flush()
        return topup
    finally:
        if own_client:
            await client.close()


async def fetch_paid_invoice_ids(client: AioCryptoPay, ids: list[int]) -> set[int]:
    """Опрос статусов инвойсов через CryptoBot. Возвращает множество оплаченных id."""
    if not ids:
        return set()
    paid: set[int] = set()
    # API позволяет передавать список invoice_ids
    invoices = await client.get_invoices(invoice_ids=ids)
    if invoices is None:
        return paid
    for inv in invoices:
        if (inv.status or "").lower() == "paid":
            paid.add(int(inv.invoice_id))
    return paid


async def find_pending_topups(session: AsyncSession, limit: int = 200) -> list[Topup]:
    res = await session.execute(
        select(Topup).where(Topup.status == TopupStatus.pending).order_by(Topup.id).limit(limit)
    )
    return list(res.scalars().all())


def parse_webhook_update(payload: dict) -> Update | None:
    try:
        return Update.model_validate(payload)
    except Exception as e:
        logger.warning("cryptobot_webhook_parse_failed", error=str(e))
        return None
