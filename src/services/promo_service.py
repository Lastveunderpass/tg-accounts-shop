from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    PromoCode,
    PromoScope,
    PromoType,
    PromoUsage,
    User,
    Variant,
)
from src.utils.money import quantize_rub


class PromoError(Exception):
    pass


async def get_promo_by_code(session: AsyncSession, code: str) -> PromoCode | None:
    res = await session.execute(select(PromoCode).where(PromoCode.code == code))
    return res.scalar_one_or_none()


async def usage_count_for_user(
    session: AsyncSession, promo_id: int, user_id: int
) -> int:
    res = await session.execute(
        select(func.count(PromoUsage.id)).where(
            PromoUsage.promo_id == promo_id, PromoUsage.user_id == user_id
        )
    )
    return int(res.scalar() or 0)


async def list_promos(
    session: AsyncSession, only_active: bool = False
) -> Sequence[PromoCode]:
    stmt = select(PromoCode).order_by(PromoCode.id.desc())
    if only_active:
        stmt = stmt.where(PromoCode.is_active.is_(True))
    res = await session.execute(stmt)
    return res.scalars().all()


async def create_promo(
    session: AsyncSession,
    *,
    code: str,
    type_: PromoType,
    value: Decimal,
    max_uses: int | None = None,
    max_uses_per_user: int | None = None,
    expires_at: datetime | None = None,
    min_order_rub: Decimal | None = None,
    scope: PromoScope = PromoScope.all,
    scope_id: int | None = None,
) -> PromoCode:
    code = code.strip().upper()
    if not code:
        raise PromoError("Код промокода не может быть пустым")
    existing = await get_promo_by_code(session, code)
    if existing is not None:
        raise PromoError(f"Промокод «{code}» уже существует")
    if value <= 0:
        raise PromoError("Значение промокода должно быть положительным")
    if type_ == PromoType.percent and value > 100:
        raise PromoError("Процент скидки не может быть больше 100")
    p = PromoCode(
        code=code,
        type=type_,
        value=value,
        max_uses=max_uses,
        max_uses_per_user=max_uses_per_user,
        used_count=0,
        expires_at=expires_at,
        min_order_rub=min_order_rub,
        scope=scope,
        scope_id=scope_id,
        is_active=True,
    )
    session.add(p)
    await session.flush()
    return p


async def deactivate_promo(session: AsyncSession, promo_id: int) -> None:
    p = await session.get(PromoCode, promo_id)
    if p is None:
        return
    p.is_active = False
    await session.flush()


async def delete_promo(session: AsyncSession, promo_id: int) -> None:
    p = await session.get(PromoCode, promo_id)
    if p is None:
        return
    await session.delete(p)
    await session.flush()


def _is_in_scope(promo: PromoCode, variant: Variant) -> bool:
    if promo.scope == PromoScope.all:
        return True
    if promo.scope == PromoScope.variant:
        return promo.scope_id == variant.id
    if promo.scope == PromoScope.product:
        return promo.scope_id == variant.product_id
    if promo.scope == PromoScope.category:
        # catalog_service.get_variant не загружает product; вызывающий код передаёт связь
        return False
    return False


async def validate_promo_for_purchase(
    session: AsyncSession,
    *,
    code: str,
    user: User,
    variant: Variant,
    subtotal_rub: Decimal,
    qty: int,
) -> tuple[PromoCode, Decimal]:
    """Проверяет промокод и возвращает (promo, скидка_рублей)."""
    promo = await get_promo_by_code(session, code.strip().upper())
    if promo is None or not promo.is_active:
        raise PromoError("Промокод не найден или неактивен")
    now = datetime.now(UTC)
    if promo.expires_at is not None and promo.expires_at < now:
        raise PromoError("Срок действия промокода истёк")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromoError("Лимит использований исчерпан")
    if promo.max_uses_per_user is not None:
        used = await usage_count_for_user(session, promo.id, user.id)
        if used >= promo.max_uses_per_user:
            raise PromoError("Вы уже использовали этот промокод")
    if promo.min_order_rub is not None and subtotal_rub < promo.min_order_rub:
        raise PromoError(f"Минимальная сумма заказа для промокода: {promo.min_order_rub} ₽")

    # scope-проверки
    if promo.scope == PromoScope.category:
        # нужно знать категорию варианта — подгружаем через Product
        from src.db.models import Product
        prod = await session.get(Product, variant.product_id)
        if prod is None or prod.category_id != promo.scope_id:
            raise PromoError("Промокод не применим к этому товару")
    else:
        if not _is_in_scope(promo, variant):
            raise PromoError("Промокод не применим к этому товару")

    if promo.type == PromoType.percent:
        discount = quantize_rub(subtotal_rub * promo.value / Decimal(100))
    elif promo.type == PromoType.fixed:
        discount = quantize_rub(promo.value)
    else:
        raise PromoError("Этот промокод можно активировать только в разделе «Промокод»")

    if discount > subtotal_rub:
        discount = subtotal_rub
    return promo, discount


async def activate_balance_promo(
    session: AsyncSession, *, code: str, user: User
) -> tuple[PromoCode, Decimal]:
    """Промокод типа `balance` активируется отдельно: +N ₽ на баланс."""
    promo = await get_promo_by_code(session, code.strip().upper())
    if promo is None or not promo.is_active:
        raise PromoError("Промокод не найден или неактивен")
    if promo.type != PromoType.balance:
        raise PromoError("Этот промокод применяется только при покупке")
    now = datetime.now(UTC)
    if promo.expires_at is not None and promo.expires_at < now:
        raise PromoError("Срок действия промокода истёк")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromoError("Лимит использований исчерпан")
    used = await usage_count_for_user(session, promo.id, user.id)
    per_user_limit = promo.max_uses_per_user if promo.max_uses_per_user is not None else 1
    if used >= per_user_limit:
        raise PromoError("Вы уже активировали этот промокод")

    amount = quantize_rub(promo.value)
    user.balance_rub = (user.balance_rub or Decimal("0")) + amount
    promo.used_count += 1
    session.add(PromoUsage(promo_id=promo.id, user_id=user.id, order_id=None))
    await session.flush()
    return promo, amount
