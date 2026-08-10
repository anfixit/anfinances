"""transaction sign invariant

Соглашение знаков (Стратегия А) держалось только на сервисном слое.
Переносим его в БД: телеграм-бот создаёт операции из распознанной
речи, где ошибка разбора вероятнее, чем ошибка в форме.

Метки transaction_kind — имена членов перечисления, заглавными.

Revision ID: e19d0sign01
Revises: e18d0fixkind
Create Date: 2026-08-10 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e19d0sign01"
down_revision: str | None = "e18d0fixkind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = {
    "ck_transactions_amount_nonzero": "amount <> 0",
    "ck_transactions_expense_negative": (
        "kind NOT IN ('EXPENSE', 'CREDIT_PAYMENT') OR amount < 0"
    ),
    "ck_transactions_income_positive": "kind <> 'INCOME' OR amount > 0",
    "ck_transactions_sign_agreement": (
        "(amount > 0 AND amount_rub > 0) OR (amount < 0 AND amount_rub < 0)"
    ),
}


def upgrade() -> None:
    # Сначала убеждаемся, что текущие данные ограничениям удовлетворяют.
    # Иначе ALTER TABLE упадёт невнятно, посреди деплоя.
    conn = op.get_bind()
    for name, condition in _CONSTRAINTS.items():
        bad = conn.execute(
            sa.text(
                "SELECT count(*) FROM transactions "  # noqa: S608
                f"WHERE NOT ({condition})"
            )
        ).scalar_one()
        if bad:
            raise RuntimeError(
                f"Нельзя добавить {name}: {bad} строк(и) в transactions "
                "нарушают соглашение знаков. Почините данные и повторите."
            )

    for name, condition in _CONSTRAINTS.items():
        op.create_check_constraint(name, "transactions", condition)


def downgrade() -> None:
    for name in _CONSTRAINTS:
        op.drop_constraint(name, "transactions", type_="check")
