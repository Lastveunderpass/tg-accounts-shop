from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_id: int = Field(..., alias="ADMIN_ID")
    support_username: str = Field(..., alias="SUPPORT_USERNAME")

    cryptobot_token: str = Field(..., alias="CRYPTOBOT_TOKEN")
    cryptobot_testnet: bool = Field(False, alias="CRYPTOBOT_TESTNET")
    cryptobot_polling: bool = Field(True, alias="CRYPTOBOT_POLLING")
    cryptobot_poll_interval: int = Field(15, alias="CRYPTOBOT_POLL_INTERVAL")
    cryptobot_base_url: str = Field("", alias="CRYPTOBOT_BASE_URL")
    cryptobot_webhook_secret: str = Field("", alias="CRYPTOBOT_WEBHOOK_SECRET")

    # Lolzteam Market — альтернативный способ оплаты (RUB через карты/СБП/Steam/Binance).
    # Минимально требуется только LOLZTEAM_TOKEN и LOLZTEAM_MERCHANT_ID; остальное опционально.
    lolzteam_token: str = Field("", alias="LOLZTEAM_TOKEN")
    lolzteam_merchant_id: int = Field(0, alias="LOLZTEAM_MERCHANT_ID")
    lolzteam_base_url: str = Field(
        "https://prod-api.lzt.market", alias="LOLZTEAM_BASE_URL"
    )
    lolzteam_polling: bool = Field(True, alias="LOLZTEAM_POLLING")
    lolzteam_poll_interval: int = Field(15, alias="LOLZTEAM_POLL_INTERVAL")
    lolzteam_invoice_lifetime: int = Field(3600, alias="LOLZTEAM_INVOICE_LIFETIME")
    lolzteam_callback_secret: str = Field("", alias="LOLZTEAM_CALLBACK_SECRET")

    default_lolzteam_enabled: bool = Field(False, alias="DEFAULT_LOLZTEAM_ENABLED")
    default_lolzteam_surcharge_percent: float = Field(
        6.0, alias="DEFAULT_LOLZTEAM_SURCHARGE_PERCENT"
    )
    default_cryptobot_enabled: bool = Field(True, alias="DEFAULT_CRYPTOBOT_ENABLED")

    database_url: str = Field("sqlite+aiosqlite:///data/db.sqlite3", alias="DATABASE_URL")

    default_referral_percent: int = Field(5, alias="DEFAULT_REFERRAL_PERCENT")
    default_min_topup_rub: int = Field(100, alias="DEFAULT_MIN_TOPUP_RUB")
    default_stock_low_threshold: int = Field(5, alias="DEFAULT_STOCK_LOW_THRESHOLD")
    default_max_qty_per_order: int = Field(10, alias="DEFAULT_MAX_QTY_PER_ORDER")

    default_notify_new_user: bool = Field(True, alias="DEFAULT_NOTIFY_NEW_USER")
    default_notify_new_topup: bool = Field(True, alias="DEFAULT_NOTIFY_NEW_TOPUP")
    default_notify_new_purchase: bool = Field(True, alias="DEFAULT_NOTIFY_NEW_PURCHASE")
    default_notify_low_stock: bool = Field(True, alias="DEFAULT_NOTIFY_LOW_STOCK")
    default_notify_refund: bool = Field(True, alias="DEFAULT_NOTIFY_REFUND")

    debug_mode: bool = Field(True, alias="DEBUG_MODE")

    tz: str = Field("Europe/Moscow", alias="TZ")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    backup_retention_days: int = Field(14, alias="BACKUP_RETENTION_DAYS")
    backup_hour: int = Field(4, alias="BACKUP_HOUR")
    backup_minute: int = Field(0, alias="BACKUP_MINUTE")

    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8080, alias="APP_PORT")

    @field_validator(
        "cryptobot_poll_interval",
        "lolzteam_merchant_id",
        "lolzteam_poll_interval",
        "lolzteam_invoice_lifetime",
        "default_referral_percent",
        "default_min_topup_rub",
        "default_stock_low_threshold",
        "default_max_qty_per_order",
        "backup_retention_days",
        "backup_hour",
        "backup_minute",
        "app_port",
        mode="before",
    )
    @classmethod
    def _empty_str_to_default(cls, v: Any, info: Any) -> Any:
        # Пустая строка в .env (например `LOLZTEAM_MERCHANT_ID=`) трактуется как
        # «использовать значение по умолчанию», а не как невалидный int.
        if isinstance(v, str) and v.strip() == "":
            field = cls.model_fields.get(info.field_name)
            if field is not None:
                return field.default
        return v

    @property
    def support_url(self) -> str:
        u = self.support_username.strip()
        if u.startswith("https://t.me/") or u.startswith("http://t.me/"):
            return u
        if u.startswith("t.me/"):
            return f"https://{u}"
        u = u.lstrip("@")
        return f"https://t.me/{u}"

    @property
    def webhook_url(self) -> str:
        if not self.cryptobot_base_url:
            return ""
        return f"{self.cryptobot_base_url.rstrip('/')}/cryptobot/webhook"

    @property
    def lolzteam_configured(self) -> bool:
        return bool(self.lolzteam_token) and self.lolzteam_merchant_id > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
