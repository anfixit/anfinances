"""add credits tables

Revision ID: c16d0credits01
Revises: b15d0af01500
Create Date: 2026-07-09 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c16d0credits01"
down_revision: str | None = "b15d0af01500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credits",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("lender", sa.String(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("principal_initial", sa.Numeric(18, 4), nullable=False),
        sa.Column("principal_balance", sa.Numeric(18, 4), nullable=False),
        sa.Column("annual_rate", sa.Numeric(9, 4), nullable=True),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("payment_day", sa.Integer(), nullable=True),
        sa.Column("linked_account_id", sa.Uuid(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.ForeignKeyConstraint(["linked_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credits_user_id", "credits", ["user_id"])
    op.create_index(
        "uq_credit_user_name_active",
        "credits",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_archived = false"),
    )

    op.create_table(
        "credit_payments",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credit_id", sa.Uuid(), nullable=False),
        sa.Column("payment_account_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("principal_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("interest_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("fee_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("interest_category_id", sa.Uuid(), nullable=True),
        sa.Column("fee_category_id", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["credit_id"], ["credits.id"]),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.ForeignKeyConstraint(["fee_category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["interest_category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["payment_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_credit_payments_credit_date",
        "credit_payments",
        ["credit_id", "date"],
    )
    op.create_index(
        "ix_credit_payments_user_date",
        "credit_payments",
        ["user_id", "date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_credit_payments_user_date",
        table_name="credit_payments",
    )
    op.drop_index(
        "ix_credit_payments_credit_date",
        table_name="credit_payments",
    )
    op.drop_table("credit_payments")
    op.drop_index("uq_credit_user_name_active", table_name="credits")
    op.drop_index("ix_credits_user_id", table_name="credits")
    op.drop_table("credits")
