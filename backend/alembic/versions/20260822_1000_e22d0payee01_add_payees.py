"""add payees

Магазин раньше жил в свободном тексте комментария операции. По такому
не сгруппировать («сколько ушло в Пятёрочку»), не найти и, главное,
не запомнить категорию: каждую выписку категории угадывались заново.

Отдельная таблица получателей плюс ссылка на неё в операции. У
получателя хранится категория последней операции — ею подставляется
категория при следующем разносе.

Уникальность — по свёрнутому имени в отдельной колонке ``name_key``:
в выписках один и тот же магазин приезжает то «Пятёрочка», то
«ПЯТЕРОЧКА». Ключ считает питон через ``casefold``, а не SQL через
``lower``: в SQLite (профиль тестов) ``lower`` не трогает кириллицу, в
PostgreSQL трогает — и тесты доказывали бы не то, что работает на
проде.

Обе внешние ссылки на удаление ставят NULL, а не каскадят: ни
удаление получателя, ни удаление категории не должно уносить с собой
операцию или запись получателя.

Данные не переносятся: разобрать двадцать форматов комментария
(«п/п 672282, card2card с карты 9561») регулярками — способ тихо
наделать мусорных получателей. Старые операции остаются без
получателя, новые получают его при вводе.

Revision ID: e22d0payee01
Revises: e21d0currency01
Create Date: 2026-08-22 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e22d0payee01"
down_revision: str | None = "e21d0currency01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payees",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False),
        sa.Column(
            "last_category_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_payees_user_id", "payees", ["user_id"])
    op.create_index(
        "uq_payee_user_name_key",
        "payees",
        ["user_id", "name_key"],
        unique=True,
    )

    op.add_column(
        "transactions",
        sa.Column(
            "payee_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("payees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("payee_name_snapshot", sa.String(), nullable=True),
    )
    op.create_index("ix_transactions_payee_id", "transactions", ["payee_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_payee_id", table_name="transactions")
    op.drop_column("transactions", "payee_name_snapshot")
    op.drop_column("transactions", "payee_id")
    op.drop_index("uq_payee_user_name_key", table_name="payees")
    op.drop_index("ix_payees_user_id", table_name="payees")
    op.drop_table("payees")
