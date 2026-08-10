"""fix credit_payment enum label

Метки типа transaction_kind — имена членов Python-перечисления
(EXPENSE, INCOME, TRANSFER), именно их отправляет SQLAlchemy.
Миграция d17d0credits02 добавила значение строчными буквами, поэтому
вставка кредитного платежа падала с "invalid input value for enum
transaction_kind: CREDIT_PAYMENT". Приводим метку к остальным.

Строк с меткой credit_payment существовать не может: чтобы такая
строка появилась, вставка должна была бы пройти — а она падала.
Поэтому переименование безопасно.

Revision ID: e18d0fixkind
Revises: d17d0credits02
Create Date: 2026-08-10 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e18d0fixkind"
down_revision: str | None = "d17d0credits02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE transaction_kind "
        "RENAME VALUE 'credit_payment' TO 'CREDIT_PAYMENT'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TYPE transaction_kind "
        "RENAME VALUE 'CREDIT_PAYMENT' TO 'credit_payment'"
    )
