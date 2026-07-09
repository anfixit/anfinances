"""add transaction snapshots

Revision ID: b15d0af01500
Revises: a1c0ffee5eed
Create Date: 2026-07-09 10:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b15d0af01500"
down_revision: str | Sequence[str] | None = "a1c0ffee5eed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("category_name_snapshot", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("subcategory_name_snapshot", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("account_name_snapshot", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("to_account_name_snapshot", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "to_account_name_snapshot")
    op.drop_column("transactions", "account_name_snapshot")
    op.drop_column("transactions", "subcategory_name_snapshot")
    op.drop_column("transactions", "category_name_snapshot")
