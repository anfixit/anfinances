"""drop user_currencies.is_default

Основная валюта пользователя хранилась в двух местах: полем
``users.default_currency`` и флагом ``user_currencies.is_default``.
Две записи одного факта расходятся молча — остаётся один источник,
поле в ``users``.

Перед удалением флаг переносится в профиль. ``default_currency``
объявлен NOT NULL с умолчанием ``'RUB'``, поэтому «пусто» там не
бывает — и проверять на пустоту бессмысленно. Значение имеет
обратный случай: флаг стоит на одной валюте, а в профиле записана
другая. Тогда выигрывает флаг: профиль мог остаться нетронутым
умолчанием, а галочку на странице валют ставят руками.

На проде обе записи совпадают (RUB), так что этот шаг там ничего не
меняет; он нужен для баз, где их успели развести.

Revision ID: e21d0currency01
Revises: e20d0credit03
Create Date: 2026-08-11 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e21d0currency01"
down_revision: str | None = "e20d0credit03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
               SET default_currency = uc.currency_code
              FROM user_currencies AS uc
             WHERE uc.user_id = users.id
               AND uc.is_default IS TRUE
               AND users.default_currency <> uc.currency_code
            """
        )
    )
    op.drop_column("user_currencies", "is_default")


def downgrade() -> None:
    op.add_column(
        "user_currencies",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Восстанавливаем флаг из единственного источника, чтобы откат
    # не оставил набор валют вообще без отметки.
    op.execute(
        sa.text(
            """
            UPDATE user_currencies AS uc
               SET is_default = TRUE
              FROM users
             WHERE users.id = uc.user_id
               AND users.default_currency = uc.currency_code
            """
        )
    )
