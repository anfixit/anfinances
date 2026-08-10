"""credit monthly payment

Обязательный ежемесячный платёж по договору. Нужен, чтобы вычислять
остаток срока: он выводится из остатка долга, ставки и платежа, а не
хранится отдельно — тогда досрочное погашение укорачивает срок само.

Revision ID: e20d0credit03
Revises: e19d0sign01
Create Date: 2026-08-10 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e20d0credit03"
down_revision: str | None = "e19d0sign01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credits",
        sa.Column("monthly_payment", sa.Numeric(18, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credits", "monthly_payment")
