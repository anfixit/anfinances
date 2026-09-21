"""payee varied categories

Память «получатель → категория» врёт на маркетплейсах: Ozon продаёт
и корм, и поводок для SUP-борда, и запомненная категория подставлялась
в каждую следующую покупку. Получатель с отметкой «разные категории»
память не пишет и не отдаёт.

Уже заведённые маркетплейсы помечаются тем же правилом, что и новые
при первой встрече, и их запомненная категория стирается: она и была
случайной.

Revision ID: e26d0payee02
Revises: e25d0kind01
Create Date: 2026-09-21 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e26d0payee02"
down_revision: str | None = "e25d0kind01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# То же правило, что is_marketplace() в сервисе получателей.
_MARKETPLACES = (
    "ozon|озон|wildberries|вайлдберриз|яндекс маркет|яндекс\\.маркет"
    "|yandex market|market\\.yandex|aliexpress|алиэкспресс|мегамаркет"
    "|megamarket"
)


def upgrade() -> None:
    op.add_column(
        "payees",
        sa.Column(
            "varied_categories",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # Шаблон — параметром, а не вклейкой в текст запроса.
    op.execute(
        sa.text(
            "UPDATE payees SET varied_categories = true, "
            "last_category_id = NULL WHERE name ~* :pattern"
        ).bindparams(pattern=_MARKETPLACES)
    )


def downgrade() -> None:
    op.drop_column("payees", "varied_categories")
