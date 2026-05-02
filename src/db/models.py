from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class ProductFormat(enum.StrEnum):
    cookies_json = "cookies_json"
    login_pass = "login_pass"
    custom_text = "custom_text"


class UploadMode(enum.StrEnum):
    zip_files = "zip_files"
    line_per_unit = "line_per_unit"
    media_group = "media_group"


class OrderStatus(enum.StrEnum):
    paid = "paid"
    refunded = "refunded"


class TopupStatus(enum.StrEnum):
    pending = "pending"
    paid = "paid"
    expired = "expired"


class PromoType(enum.StrEnum):
    percent = "percent"
    fixed = "fixed"
    balance = "balance"


class PromoScope(enum.StrEnum):
    all = "all"
    category = "category"
    product = "product"
    variant = "variant"


class CryptoAsset(enum.StrEnum):
    USDT = "USDT"
    TON = "TON"
    BTC = "BTC"
    LTC = "LTC"


class PaymentProvider(enum.StrEnum):
    cryptobot = "cryptobot"
    lolzteam = "lolzteam"


# ─────────────────────────────────────────── User ───────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    total_spent_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ref_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    ref_earned_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    referrer: Mapped[User | None] = relationship(
        "User", remote_side="User.id", foreign_keys=[referrer_id]
    )


# ─────────────────────────────────────────── Catalog ───────────────────────────────────────────
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    products: Mapped[list[Product]] = relationship(
        "Product", back_populates="category", cascade="all, delete-orphan"
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    format: Mapped[ProductFormat] = mapped_column(
        SAEnum(ProductFormat, name="product_format"),
        nullable=False,
        default=ProductFormat.cookies_json,
    )
    upload_mode: Mapped[UploadMode] = mapped_column(
        SAEnum(UploadMode, name="upload_mode"), nullable=False, default=UploadMode.zip_files
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    category: Mapped[Category] = relationship("Category", back_populates="products")
    variants: Mapped[list[Variant]] = relationship(
        "Variant", back_populates="product", cascade="all, delete-orphan"
    )


class Variant(Base):
    __tablename__ = "variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship("Product", back_populates="variants")
    stock_items: Mapped[list[StockItem]] = relationship(
        "StockItem", back_populates="variant", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────── Stock ───────────────────────────────────────────
class StockBatch(Base):
    __tablename__ = "stock_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    items_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_sold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    sold_to_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    variant: Mapped[Variant] = relationship("Variant", back_populates="stock_items")

    __table_args__ = (
        Index("ix_stock_unsold", "variant_id", "is_sold"),
    )


# ─────────────────────────────────────────── Orders ───────────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), nullable=False, default=OrderStatus.paid
    )
    subtotal_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_rub: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    total_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    promo_code_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    refund_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("variants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stock_item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_items.id", ondelete="SET NULL"), nullable=True
    )
    unit_price_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="items")


# ─────────────────────────────────────────── Topup ───────────────────────────────────────────
class Topup(Base):
    __tablename__ = "topups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Способ оплаты. Для cryptobot заполнены crypto_*, для lolzteam — lolzteam_*.
    provider: Mapped[PaymentProvider] = mapped_column(
        SAEnum(PaymentProvider, name="payment_provider"),
        nullable=False,
        default=PaymentProvider.cryptobot,
        index=True,
    )
    # CryptoBot-специфичные поля (NULL для lolzteam).
    crypto_asset: Mapped[CryptoAsset | None] = mapped_column(
        SAEnum(CryptoAsset, name="crypto_asset"), nullable=True
    )
    crypto_amount: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    crypto_rate_rub: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    cryptobot_invoice_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True, index=True
    )
    # Lolzteam-специфичные поля (NULL для cryptobot).
    lolzteam_invoice_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True, index=True
    )
    lolzteam_payment_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    # Сумма к оплате с учётом наценки провайдера (для lolzteam — amount_rub * 1.06).
    # Для cryptobot равно amount_rub (наценки нет).
    gross_amount_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Зафиксированная при создании наценка, %. Чтобы старые инвойсы не пересчитывались
    # после смены настройки.
    surcharge_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    pay_url: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[TopupStatus] = mapped_column(
        SAEnum(TopupStatus, name="topup_status"), nullable=False, default=TopupStatus.pending, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ──────────────────────────────────── Promo / Referral ────────────────────────────────────
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    type: Mapped[PromoType] = mapped_column(SAEnum(PromoType, name="promo_type"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    min_order_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    scope: Mapped[PromoScope] = mapped_column(
        SAEnum(PromoScope, name="promo_scope"), nullable=False, default=PromoScope.all
    )
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PromoUsage(Base):
    __tablename__ = "promo_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("promo_id", "user_id", "order_id", name="uq_promo_usage"),)


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topup_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topups.id", ondelete="CASCADE"), nullable=False
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ──────────────────────────────────── Subscriptions / Settings ────────────────────────────────────
class StockSubscription(Base):
    __tablename__ = "stock_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "variant_id", name="uq_stock_sub_user_variant"),
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
