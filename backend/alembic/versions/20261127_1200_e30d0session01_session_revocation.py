"""auth: rotated_at у refresh-токена, sessions_revoked_at у пользователя

rotated_at — когда токен заменён новым при обновлении сессии. Отличает
ротацию от выхода и отзыва: повтор ротированного токена в первые
секунды — это вторая вкладка, а не кража.

sessions_revoked_at — когда пользователь завершил все сессии (сменил
пароль или «вышел везде»). Access-токены, выпущенные раньше, с этого
момента не принимаются, хотя их срок ещё не истёк.

Обе колонки nullable без умолчаний: старый код их не знает и не
трогает, так что миграция совместима с ним (выполняется до запуска
нового кода).

Revision ID: e30d0session01
Revises: e29d0trash01
Create Date: 2026-11-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e30d0session01"
down_revision: str | None = "e29d0trash01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "sessions_revoked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_revoked_at")
    op.drop_column("refresh_tokens", "rotated_at")
