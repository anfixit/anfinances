"""add reconciliation

Сверка ловит то, чего не видно в списке операций: задвоенный платёж,
потерянную трату, перевод, у которого записали одну ногу. Всё это
незаметно построчно и сразу заметно в остатке.

Таблица хранит по одной строке на сверку: что показал банк, что было
записано и какой корректирующей операцией закрыли разницу, если
закрывали. У операций появляется отметка ``reconciled_at`` — до
какого момента всё проверено.

Отметка, а не замок: цена ошибочной блокировки — «не могу исправить
свои же данные», это хуже незамеченной правки старого.

Ссылка на корректирующую операцию на удаление ставит NULL: удалённая
операция не должна уносить с собой запись о самой сверке.

Revision ID: e23d0recon01
Revises: e22d0payee01
Create Date: 2026-08-22 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e23d0recon01"
down_revision: str | None = "e22d0payee01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reconciliations",
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
        sa.Column(
            "account_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("statement_balance", sa.Numeric(18, 4), nullable=False),
        sa.Column("computed_balance", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "adjustment_transaction_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="SET NULL"),
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
    op.create_index(
        "ix_reconciliations_user_id", "reconciliations", ["user_id"]
    )
    op.create_index(
        "ix_reconciliations_account_id", "reconciliations", ["account_id"]
    )

    op.add_column(
        "transactions",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "reconciled_at")
    op.drop_index(
        "ix_reconciliations_account_id", table_name="reconciliations"
    )
    op.drop_index("ix_reconciliations_user_id", table_name="reconciliations")
    op.drop_table("reconciliations")
