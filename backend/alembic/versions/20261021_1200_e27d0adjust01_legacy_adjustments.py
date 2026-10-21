"""legacy adjustments become real adjustments

До типа ADJUSTMENT правки остатка записывались тратой или доходом в
категорию «Корректировка» («Корректировка баланса»). Они до сих пор
сидят в расходах и доходах: в октябре такая «трата» на 1 007,56 ₽
висела в бюджете строкой без лимита и портила графики.

Операции в таких категориях становятся корректировками. Сумма и её
знак не меняются — остатки счетов те же; уходит только категория,
как у всякой корректировки. Переводы и платежи по кредиту не
трогаются.

Опустевшая категория уходит в архив, но лишь когда на ней ничего не
держится: ни подкатегорий, ни бюджетов, ни плана-минимума, ни цели.
Иначе остаётся как есть — убрать её можно руками. Запомненная за
получателями категория стирается, чтобы бот не подставлял её снова.

Шаблон регистра — явный «[Кк]»: ~* в базе с локалью C кириллицу без
учёта регистра не сравнивает.

Обратно не откатывается: какие корректировки были тратой, а какие
доходом, после миграции не восстановить — и незачем.

Revision ID: e27d0adjust01
Revises: e26d0payee02
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e27d0adjust01"
down_revision: str | None = "e26d0payee02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PATTERN = "^[Кк]орректировк"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE transactions SET kind = 'ADJUSTMENT', "
            "category_id = NULL, required = NULL, "
            "category_name_snapshot = NULL, "
            "subcategory_name_snapshot = NULL "
            "WHERE transfer_id IS NULL "
            "AND CAST(kind AS TEXT) IN ('EXPENSE', 'INCOME') "
            "AND ("
            "  category_id IN (SELECT id FROM categories WHERE name ~ :p) "
            "  OR (category_id IS NULL AND ("
            "    category_name_snapshot ~ :p "
            "    OR subcategory_name_snapshot ~ :p))"
            ")"
        ).bindparams(p=_PATTERN)
    )
    op.execute(
        sa.text(
            "UPDATE payees SET last_category_id = NULL "
            "WHERE last_category_id IN "
            "(SELECT id FROM categories WHERE name ~ :p)"
        ).bindparams(p=_PATTERN)
    )
    op.execute(
        sa.text(
            "UPDATE categories AS c SET is_archived = true "
            "WHERE c.name ~ :p AND c.is_archived = false "
            "AND NOT EXISTS (SELECT 1 FROM categories AS ch "
            "  WHERE ch.parent_id = c.id AND ch.is_archived = false) "
            "AND NOT EXISTS (SELECT 1 FROM budgets AS b "
            "  WHERE b.category_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM recurring_expenses AS r "
            "  WHERE r.category_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM category_goals AS g "
            "  WHERE g.category_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM transactions AS t "
            "  WHERE t.category_id = c.id)"
        ).bindparams(p=_PATTERN)
    )


def downgrade() -> None:
    # Данные назад не разворачиваются — см. описание миграции.
    pass
