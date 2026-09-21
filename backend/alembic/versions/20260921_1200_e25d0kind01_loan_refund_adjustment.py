"""loan, refund and adjustment transaction kinds

Операция бывала только доходом или расходом. Кредит на 430 000,
возвраты с Ozon и из аптеки, правки после сверок — всё писалось
доходом, и график за сентябрь показал +331 704 ₽ при настоящем
−98 844 ₽.

Три новых типа — деньги, которые приходят или правятся, но не
являются ни заработком, ни тратой. Кредит и возврат всегда приход,
это закреплено ограничением. Корректировка бывает любого знака.

Значения enum PostgreSQL удалять не умеет, поэтому downgrade снимает
только ограничение; значения остаются и никому не мешают. IF NOT
EXISTS делает повторный upgrade безопасным.

Revision ID: e25d0kind01
Revises: e24d0goal01
Create Date: 2026-09-21 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e25d0kind01"
down_revision: str | None = "e24d0goal01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Метки в БД — имена членов перечисления, заглавными.
    for label in ("LOAN", "REFUND", "ADJUSTMENT"):
        op.execute(
            f"ALTER TYPE transaction_kind ADD VALUE IF NOT EXISTS '{label}'"
        )
    op.create_check_constraint(
        "ck_transactions_inflow_positive",
        "transactions",
        "CAST(kind AS TEXT) NOT IN ('LOAN', 'REFUND') OR amount > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_transactions_inflow_positive", "transactions", type_="check"
    )
