"""topup payment provider

Revision ID: 0003_topup_provider
Revises: 0002_product_image
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_topup_provider"
down_revision = "0002_product_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite не поддерживает добавление UNIQUE inline через batch_alter_table в один шаг
    # одновременно с CHECK на enum'ах, поэтому делаем явный batch.
    with op.batch_alter_table("topups") as batch:
        # Все CryptoBot-специфичные поля становятся nullable, чтобы Lolzteam-инвойсы
        # могли их не заполнять.
        batch.alter_column("crypto_asset", existing_type=sa.String(), nullable=True)
        batch.alter_column("crypto_amount", existing_type=sa.Numeric(36, 18), nullable=True)
        batch.alter_column("crypto_rate_rub", existing_type=sa.Numeric(36, 18), nullable=True)
        batch.alter_column(
            "cryptobot_invoice_id", existing_type=sa.BigInteger(), nullable=True
        )

        batch.add_column(
            sa.Column(
                "provider",
                sa.String(length=32),
                nullable=False,
                server_default="cryptobot",
            )
        )
        batch.add_column(sa.Column("lolzteam_invoice_id", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column("lolzteam_payment_id", sa.String(length=64), nullable=True)
        )
        batch.add_column(sa.Column("gross_amount_rub", sa.Numeric(18, 2), nullable=True))
        batch.add_column(sa.Column("surcharge_percent", sa.Numeric(5, 2), nullable=True))

        batch.create_unique_constraint(
            "uq_topups_lolzteam_invoice_id", ["lolzteam_invoice_id"]
        )
        batch.create_unique_constraint(
            "uq_topups_lolzteam_payment_id", ["lolzteam_payment_id"]
        )

    op.create_index(
        "ix_topups_provider", "topups", ["provider"]
    )
    op.create_index(
        "ix_topups_lolzteam_invoice_id", "topups", ["lolzteam_invoice_id"]
    )
    op.create_index(
        "ix_topups_lolzteam_payment_id", "topups", ["lolzteam_payment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_topups_lolzteam_payment_id", table_name="topups")
    op.drop_index("ix_topups_lolzteam_invoice_id", table_name="topups")
    op.drop_index("ix_topups_provider", table_name="topups")
    with op.batch_alter_table("topups") as batch:
        batch.drop_constraint("uq_topups_lolzteam_payment_id", type_="unique")
        batch.drop_constraint("uq_topups_lolzteam_invoice_id", type_="unique")
        batch.drop_column("surcharge_percent")
        batch.drop_column("gross_amount_rub")
        batch.drop_column("lolzteam_payment_id")
        batch.drop_column("lolzteam_invoice_id")
        batch.drop_column("provider")
        batch.alter_column(
            "cryptobot_invoice_id", existing_type=sa.BigInteger(), nullable=False
        )
        batch.alter_column(
            "crypto_rate_rub", existing_type=sa.Numeric(36, 18), nullable=False
        )
        batch.alter_column(
            "crypto_amount", existing_type=sa.Numeric(36, 18), nullable=False
        )
        batch.alter_column("crypto_asset", existing_type=sa.String(), nullable=False)
