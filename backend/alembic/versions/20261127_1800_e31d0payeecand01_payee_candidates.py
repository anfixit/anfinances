"""payee candidates

Таблица кандидатов в получатели: имя, которое встретилось в операции,
но ещё не принято в справочник. Ждёт решения владелицы (``pending``)
или отклонено (``rejected``).

Уникальность — по свёрнутому имени ``name_key``, как у ``payees``;
ключ считает питон через ``casefold``, не SQL ``lower``.

Только новая таблица: старый код её не знает и не трогает, миграция
совместима с ним.

Revision ID: e31d0payeecand01
Revises: e30d0session01
Create Date: 2026-11-27 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e31d0payeecand01"
down_revision: str | None = "e30d0session01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payee_candidates",
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
            "status",
            sa.String(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "times_seen",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
        "ix_payee_candidates_user_id", "payee_candidates", ["user_id"]
    )
    op.create_index(
        "uq_payee_candidate_user_name_key",
        "payee_candidates",
        ["user_id", "name_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_payee_candidate_user_name_key", table_name="payee_candidates"
    )
    op.drop_index("ix_payee_candidates_user_id", table_name="payee_candidates")
    op.drop_table("payee_candidates")
