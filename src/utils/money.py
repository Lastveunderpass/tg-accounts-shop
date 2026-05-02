from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal

CRYPTO_PRECISION: dict[str, int] = {
    "USDT": 2,
    "TON": 4,
    "BTC": 8,
    "LTC": 8,
}


def quantize_rub(value: Decimal | int | float | str) -> Decimal:
    """Округляет рубли до копеек (стандартный half-up)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def crypto_charge_amount(amount_rub: Decimal, rate_rub_per_unit: Decimal, asset: str) -> Decimal:
    """
    Сколько крипты должен заплатить юзер за `amount_rub` рублей.
    Округление **в пользу сервиса** (вверх).
    `rate_rub_per_unit` — сколько рублей стоит 1 единица крипты (USDT/TON/BTC/LTC).
    """
    if rate_rub_per_unit <= 0:
        raise ValueError("Курс должен быть положительным")
    raw = Decimal(amount_rub) / Decimal(rate_rub_per_unit)
    precision = CRYPTO_PRECISION.get(asset, 8)
    quantum = Decimal(1).scaleb(-precision)
    return raw.quantize(quantum, rounding=ROUND_UP)


def floor_rub(value: Decimal | int | float | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def percent_of(amount: Decimal, percent: Decimal | int | float) -> Decimal:
    """`amount * percent / 100`, округляем рубли в пользу сервиса (down) при списании,
    а здесь возвращаем half-up — для скидок и реф. процентов берём как стандарт."""
    return quantize_rub(Decimal(amount) * Decimal(percent) / Decimal(100))


def fmt_rub(value: Decimal | int | float | str) -> str:
    d = quantize_rub(value)
    int_part, _, frac_part = f"{d:.2f}".partition(".")
    if frac_part == "00":
        return f"{int_part} ₽"
    return f"{int_part}.{frac_part} ₽"


def fmt_crypto(value: Decimal | int | float | str, asset: str) -> str:
    precision = CRYPTO_PRECISION.get(asset, 8)
    d = Decimal(value).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_UP)
    s = f"{d:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s} {asset}"
