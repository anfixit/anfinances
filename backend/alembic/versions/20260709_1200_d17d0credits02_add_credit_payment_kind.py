"""add credit payment transaction kind

Revision ID: d17d0credits02
Revises: c16d0credits01
Create Date: 2026-07-09 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d17d0credits02"
down_revision: str | None = "c16d0credits01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE transaction_kind ADD VALUE IF NOT EXISTS 'credit_payment'"
    )


def downgrade() -> None:
    # PostgreSQL не умеет безопасно удалять значение из enum без
    # пересоздания типа и переписывания таблиц. Оставляем no-op.
    pass
