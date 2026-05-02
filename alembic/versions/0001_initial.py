"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-02 00:00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("balance_rub", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_spent_rub", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("referrer_id", sa.BigInteger(), nullable=True),
        sa.Column("ref_code", sa.String(length=32), nullable=False),
        sa.Column("ref_earned_rub", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref_code"),
    )
    op.create_index("ix_users_referrer_id", "users", ["referrer_id"])
    op.create_index("ix_users_ref_code", "users", ["ref_code"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "format",
            sa.Enum("cookies_json", "login_pass", "custom_text", name="product_format"),
            nullable=False,
            server_default="cookies_json",
        ),
        sa.Column(
            "upload_mode",
            sa.Enum("zip_files", "line_per_unit", "media_group", name="upload_mode"),
            nullable=False,
            server_default="zip_files",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])

    op.create_table(
        "variants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_variants_product_id", "variants", ["product_id"])

    op.create_table(
        "stock_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("items_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_batches_variant_id", "stock_batches", ["variant_id"])

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "type",
            sa.Enum("percent", "fixed", "balance", name="promo_type"),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("max_uses_per_user", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("min_order_rub", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "scope",
            sa.Enum("all", "category", "product", "variant", name="promo_scope"),
            nullable=False,
            server_default="all",
        ),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("paid", "refunded", name="order_status"),
            nullable=False,
            server_default="paid",
        ),
        sa.Column("subtotal_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_rub", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column("promo_code_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_by_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("refund_note", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("stock_item_id", sa.Integer(), nullable=True),
        sa.Column("unit_price_rub", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_variant_id", "order_items", ["variant_id"])

    op.create_table(
        "stock_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("is_sold", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sold_to_user_id", sa.BigInteger(), nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_item_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["stock_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sold_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_items_variant_id", "stock_items", ["variant_id"])
    op.create_index("ix_stock_items_is_sold", "stock_items", ["is_sold"])
    op.create_index("ix_stock_items_batch_id", "stock_items", ["batch_id"])
    op.create_index("ix_stock_unsold", "stock_items", ["variant_id", "is_sold"])

    op.create_table(
        "topups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "crypto_asset",
            sa.Enum("USDT", "TON", "BTC", "LTC", name="crypto_asset"),
            nullable=False,
        ),
        sa.Column("crypto_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("crypto_rate_rub", sa.Numeric(36, 18), nullable=False),
        sa.Column("cryptobot_invoice_id", sa.BigInteger(), nullable=False),
        sa.Column("pay_url", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "paid", "expired", name="topup_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cryptobot_invoice_id"),
    )
    op.create_index("ix_topups_user_id", "topups", ["user_id"])
    op.create_index("ix_topups_status", "topups", ["status"])
    op.create_index("ix_topups_cryptobot_invoice_id", "topups", ["cryptobot_invoice_id"])

    op.create_table(
        "promo_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("promo_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["promo_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("promo_id", "user_id", "order_id", name="uq_promo_usage"),
    )
    op.create_index("ix_promo_usages_promo_id", "promo_usages", ["promo_id"])
    op.create_index("ix_promo_usages_user_id", "promo_usages", ["user_id"])

    op.create_table(
        "referral_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("referrer_id", sa.BigInteger(), nullable=False),
        sa.Column("referee_id", sa.BigInteger(), nullable=False),
        sa.Column("topup_id", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referee_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topup_id"], ["topups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_referral_events_referrer_id", "referral_events", ["referrer_id"])
    op.create_index("ix_referral_events_referee_id", "referral_events", ["referee_id"])

    op.create_table(
        "stock_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "variant_id", name="uq_stock_sub_user_variant"),
    )
    op.create_index("ix_stock_subscriptions_user_id", "stock_subscriptions", ["user_id"])
    op.create_index("ix_stock_subscriptions_variant_id", "stock_subscriptions", ["variant_id"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("broadcasts")
    op.drop_table("settings")
    op.drop_index("ix_stock_subscriptions_variant_id", table_name="stock_subscriptions")
    op.drop_index("ix_stock_subscriptions_user_id", table_name="stock_subscriptions")
    op.drop_table("stock_subscriptions")
    op.drop_index("ix_referral_events_referee_id", table_name="referral_events")
    op.drop_index("ix_referral_events_referrer_id", table_name="referral_events")
    op.drop_table("referral_events")
    op.drop_index("ix_promo_usages_user_id", table_name="promo_usages")
    op.drop_index("ix_promo_usages_promo_id", table_name="promo_usages")
    op.drop_table("promo_usages")
    op.drop_index("ix_topups_cryptobot_invoice_id", table_name="topups")
    op.drop_index("ix_topups_status", table_name="topups")
    op.drop_index("ix_topups_user_id", table_name="topups")
    op.drop_table("topups")
    op.drop_index("ix_stock_unsold", table_name="stock_items")
    op.drop_index("ix_stock_items_batch_id", table_name="stock_items")
    op.drop_index("ix_stock_items_is_sold", table_name="stock_items")
    op.drop_index("ix_stock_items_variant_id", table_name="stock_items")
    op.drop_table("stock_items")
    op.drop_index("ix_order_items_variant_id", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_index("ix_stock_batches_variant_id", table_name="stock_batches")
    op.drop_table("stock_batches")
    op.drop_index("ix_variants_product_id", table_name="variants")
    op.drop_table("variants")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_index("ix_users_ref_code", table_name="users")
    op.drop_index("ix_users_referrer_id", table_name="users")
    op.drop_table("users")
