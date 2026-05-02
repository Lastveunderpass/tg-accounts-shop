"""Тонкая обёртка над Lolzteam Market API (POST /invoice / GET /invoice).

Документация: https://lzt-market.readme.io/reference. Авторизация — Bearer-токен
с правом `payment` (выдаётся в lolz.live → Account upgrades → API).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from src.config import get_settings
from src.logger import get_logger

logger = get_logger("lolzteam.client")


class LolzteamError(RuntimeError):
    """Ошибка от Lolzteam Market API."""


class LolzteamClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        s = get_settings()
        self._token = token or s.lolzteam_token
        self._base_url = (base_url or s.lolzteam_base_url).rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> LolzteamClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        client = self._ensure_client()
        # Lolzteam ожидает параметры в query string даже для POST.
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = await client.request(method, path, params=clean)
        except httpx.HTTPError as e:
            raise LolzteamError(f"Сетевая ошибка Lolzteam: {e}") from e
        if resp.status_code >= 400:
            raise LolzteamError(
                f"Lolzteam API {resp.status_code}: {resp.text[:300]}"
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise LolzteamError(f"Невалидный JSON от Lolzteam: {e}") from e
        if not isinstance(data, dict):
            raise LolzteamError(f"Неожиданный ответ Lolzteam: {data!r}")
        # На некоторые ошибки API возвращает 200 с полем `errors`.
        errors = data.get("errors")
        if errors:
            raise LolzteamError(f"Lolzteam API errors: {errors}")
        return data

    async def create_invoice(
        self,
        *,
        amount: Decimal,
        payment_id: str,
        comment: str,
        merchant_id: int,
        url_success: str,
        url_callback: str | None = None,
        currency: str = "rub",
        lifetime: int = 3600,
        additional_data: str | None = None,
    ) -> dict[str, Any]:
        """POST /invoice. Возвращает тело ответа (вкл. `invoice`)."""
        params = {
            "currency": currency,
            "amount": float(amount),
            "payment_id": payment_id,
            "comment": comment,
            "merchant_id": merchant_id,
            "url_success": url_success,
            "url_callback": url_callback,
            "lifetime": lifetime,
            "additional_data": additional_data,
        }
        return await self._request("POST", "/invoice", params=params)

    async def get_invoice(
        self, *, invoice_id: int | None = None, payment_id: str | None = None
    ) -> dict[str, Any]:
        if invoice_id is None and payment_id is None:
            raise ValueError("Нужен invoice_id или payment_id")
        params = {"invoice_id": invoice_id, "payment_id": payment_id}
        return await self._request("GET", "/invoice", params=params)

    async def list_invoices(
        self,
        *,
        merchant_id: int,
        status: str | None = "paid",
        page: int = 1,
        amount: float | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "merchant_id": merchant_id,
            "status": status,
            "page": page,
            "amount": amount,
            "currency": currency,
        }
        return await self._request("GET", "/invoice/list", params=params)


def extract_invoice(data: dict[str, Any]) -> dict[str, Any]:
    """API возвращает либо `{"invoice": {...}}`, либо сам инвойс плоско —
    нормализуем."""
    if "invoice" in data and isinstance(data["invoice"], dict):
        return data["invoice"]
    return data


def extract_invoices(data: dict[str, Any]) -> list[dict[str, Any]]:
    """list_invoices возвращает `{"invoices": [...]}` (или ключ `data`)."""
    for key in ("invoices", "data", "items"):
        v = data.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def is_paid(invoice: dict[str, Any]) -> bool:
    status = str(invoice.get("status", "")).lower()
    return status in ("paid", "success", "successful", "completed")


def invoice_pay_url(invoice: dict[str, Any]) -> str:
    """Lolzteam в разное время называет эту ссылку по-разному; ищем все варианты."""
    for key in ("url", "page_url", "payment_url", "pay_url", "checkout_url"):
        v = invoice.get(key)
        if isinstance(v, str) and v:
            return v
    invoice_id = invoice.get("invoice_id") or invoice.get("id")
    if invoice_id is not None:
        return f"https://lzt.market/invoice/{invoice_id}"
    return ""
