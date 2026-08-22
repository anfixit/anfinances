"""add category goals

Копилки уже были: конверт с rollover копит остаток из месяца в месяц.
Чего не было — ответа на вопрос «сколько положить в этом месяце».
Его приходилось считать в голове, а значит не считать вовсе.

Цель хранит, сколько нужно и к какому сроку; взнос текущего месяца
считается на лету от уже накопленного.

Одна цель на категорию: две цели на один конверт — это два разных
ответа на один вопрос.

Категория удаляется каскадом: цель без категории бессмысленна, а
осиротевшая строка ломала бы расчёт.

Revision ID: e24d0goal01
Revises: e23d0recon01
Create Date: 2026-08-22 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e24d0goal01"
down_revision: str | None = "e23d0recon01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Тип создаёт сам create_table, как в первой миграции проекта.
    # Отдельный Enum.create() рядом с ним даёт DuplicateObject: тип
    # заводится дважды за один прогон.
    op.create_table(
        "category_goals",
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
            "category_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM("MONTHLY", "BY_DATE", name="goal_kind"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
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
        sa.UniqueConstraint(
            "user_id", "category_id", name="uq_goal_user_category"
        ),
    )
    op.create_index("ix_category_goals_user_id", "category_goals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_category_goals_user_id", table_name="category_goals")
    op.drop_table("category_goals")
    # Таблицу create_table снесла, а тип за собой не убирает.
    sa.Enum(name="goal_kind").drop(op.get_bind(), checkfirst=True)
