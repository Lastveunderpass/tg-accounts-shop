"""Высокоуровневые операции с Lolzteam-инвойсами в БД."""

from __future__ import annotations

import uuid
from decimal import ROUND_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import PaymentProvider, Topup, TopupStatus
from src.logger import get_logger
from src.services import lolzteam_client, settings_service
from src.services.lolzteam_client import (
    LolzteamClient,
    LolzteamError,
    extract_invoice,
    invoice_pay_url,
)
from src.utils.money import quantize_rub

logger = get_logger("lolzteam")


def _round_up_rub(value: Decimal) -> Decimal:
    """Округление вверх до копеек — в пользу сервиса."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_UP)


async def calc_gross_amount(
    session: AsyncSession, *, amount_rub: Decimal
) -> tuple[Decimal, Decimal]:
    """Возвращает (gross_amount, surcharge_percent)."""
    raw = await settings_service.get_setting(session, "lolzteam_surcharge_percent", "6")
    try:
        surcharge = Decimal(str(raw))
    except Exception:
        surcharge = Decimal("6")
    if surcharge < 0:
        surcharge = Decimal("0")
    gross = _round_up_rub(amount_rub * (Decimal("1") + surcharge / Decimal("100")))
    return gross, surcharge


async def create_topup_invoice(
    session: AsyncSession,
    *,
    user_id: int,
    amount_rub: Decimal,
    bot_username: str,
    client: LolzteamClient | None = None,
) -> Topup:
    """Создаёт инвойс на Lolzteam и Topup-запись со статусом pending."""
    settings = get_settings()
    if not settings.lolzteam_configured:
        raise LolzteamError("Lolzteam не настроен (нет токена или merchant_id)")

    amount_rub = quantize_rub(amount_rub)
    gross, surcharge = await calc_gross_amount(session, amount_rub=amount_rub)
    payment_id = uuid.uuid4().hex[:32]

    own_client = client is None
    if client is None:
        client = LolzteamClient()
    try:
        callback_url = ""
        if settings.cryptobot_base_url:
            callback_url = (
                f"{settings.cryptobot_base_url.rstrip('/')}/lolzteam/webhook"
            )
        success_url = (
            f"https://t.me/{bot_username.lstrip('@')}" if bot_username else "https://lzt.market"
        )
        comment = f"Пополнение баланса на {amount_rub} ₽"
        try:
            data = await client.create_invoice(
                amount=gross,
                payment_id=payment_id,
                comment=comment,
                merchant_id=settings.lolzteam_merchant_id,
                url_success=success_url,
                url_callback=callback_url or None,
                lifetime=settings.lolzteam_invoice_lifetime,
            )
        except LolzteamError:
            raise
    finally:
        if own_client:
            await client.close()

    invoice = extract_invoice(data)
    invoice_id_raw = invoice.get("invoice_id") or invoice.get("id")
    if invoice_id_raw is None:
        raise LolzteamError(f"Lolzteam не вернул invoice_id: {data}")
    invoice_id = int(invoice_id_raw)
    pay_url = invoice_pay_url(invoice)
    if not pay_url:
        raise LolzteamError(f"Lolzteam не вернул URL оплаты: {data}")

    topup = Topup(
        user_id=user_id,
        amount_rub=amount_rub,
        provider=PaymentProvider.lolzteam,
        lolzteam_invoice_id=invoice_id,
        lolzteam_payment_id=payment_id,
        gross_amount_rub=gross,
        surcharge_percent=surcharge,
        pay_url=pay_url,
        status=TopupStatus.pending,
    )
    session.add(topup)
    await session.flush()
    return topup


async def find_pending_topups(session: AsyncSession, limit: int = 200) -> list[Topup]:
    res = await session.execute(
        select(Topup)
        .where(
            Topup.status == TopupStatus.pending,
            Topup.provider == PaymentProvider.lolzteam,
        )
        .order_by(Topup.id)
        .limit(limit)
    )
    return list(res.scalars().all())


async def fetch_paid_invoice_ids(
    client: LolzteamClient, *, merchant_id: int, candidate_ids: list[int]
) -> set[int]:
    """Возвращает множество invoice_id, которые помечены как paid у мерчанта."""
    if not candidate_ids:
        return set()
    paid: set[int] = set()
    candidate_set = set(candidate_ids)

    # Сначала идём по списку платных через /invoice/list — одним запросом получаем
    # последние оплаченные. Если новых не нашли — фолбэк на поштучный GET /invoice.
    try:
        data = await client.list_invoices(merchant_id=merchant_id, status="paid", page=1)
        for inv in lolzteam_client.extract_invoices(data):
            inv_id_raw = inv.get("invoice_id") or inv.get("id")
            if inv_id_raw is None:
                continue
            inv_id = int(inv_id_raw)
            if inv_id in candidate_set and lolzteam_client.is_paid(inv):
                paid.add(inv_id)
    except LolzteamError as e:
        logger.warning("lolzteam_list_failed", error=str(e))

    # Поштучный фолбэк (медленный, но надёжный) для тех, что не нашли в списке.
    for inv_id in candidate_ids:
        if inv_id in paid:
            continue
        try:
            data = await client.get_invoice(invoice_id=inv_id)
            inv = extract_invoice(data)
            if lolzteam_client.is_paid(inv):
                paid.add(inv_id)
        except LolzteamError as e:
            logger.warning("lolzteam_get_failed", invoice_id=inv_id, error=str(e))
    return paid
