"""trash: deleted_records — корзина удалённых операций

Удалённая операция, перевод (узел и все ноги) или платёж по кредиту
(платёж и его списание) ложится сюда одной строкой: копия строк в
payload, человеческое описание в summary и кто удалил. Возврат
вставляет строки обратно с теми же id.

Вид (kind) — строка, а не enum PostgreSQL: новый вид не должен
требовать миграции типа. ai_connection_id — без внешнего ключа:
отзыв подключения не должен стирать след того, что оно удаляло.

Revision ID: e29d0trash01
Revises: e28d0aiaccess01
Create Date: 2026-11-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e29d0trash01"
down_revision: str | None = "e28d0aiaccess01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deleted_records",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("ai_connection_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_deleted_records_user_deleted",
        "deleted_records",
        ["user_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deleted_records_user_deleted", table_name="deleted_records"
    )
    op.drop_table("deleted_records")
