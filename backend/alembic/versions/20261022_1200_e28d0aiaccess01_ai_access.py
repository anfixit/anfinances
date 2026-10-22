"""ai access: connections, tokens, oauth codes and clients

ИИ-ассистенты (ChatGPT, Claude) получают доступ к данным через
MCP-сервер. Доступ выдаётся либо OAuth-авторизацией из самого
ассистента, либо личным токеном, созданным в настройках.

ai_connections — одно разрешение, которое пользователь видит в
настройках и может отозвать. ai_tokens — его токены (личный,
access, refresh); хранится только SHA-256, сам токен показывается
один раз. ai_oauth_codes — одноразовые коды авторизации.
ai_oauth_clients — клиенты, зарегистрированные динамически.

Виды (kind) — строки, а не enum PostgreSQL: новый вид не должен
требовать миграции типа.

Удаление пользователя уносит его подключения, токены и коды
каскадом: доступ к данным, которых больше нет, бессмыслен.

Revision ID: e28d0aiaccess01
Revises: e27d0adjust01
Create Date: 2026-10-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e28d0aiaccess01"
down_revision: str | None = "e27d0adjust01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[object]:
    return sa.Column(
        "id",
        sa.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        _id(),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("client_id", sa.String(2000), nullable=True),
        sa.Column("scopes", sa.String(200), nullable=False),
        sa.Column("resource", sa.String(2000), nullable=True),
        _created_at(),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_connections_user_id", "ai_connections", ["user_id"])

    op.create_table(
        "ai_tokens",
        _id(),
        sa.Column(
            "connection_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("ai_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index(
        "ix_ai_tokens_connection_id", "ai_tokens", ["connection_id"]
    )

    op.create_table(
        "ai_oauth_codes",
        _id(),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(2000), nullable=False),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("redirect_uri", sa.String(2000), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("scopes", sa.String(200), nullable=False),
        sa.Column("resource", sa.String(2000), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "connection_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("ai_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )

    op.create_table(
        "ai_oauth_clients",
        _id(),
        sa.Column("client_id", sa.String(64), nullable=False, unique=True),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        _created_at(),
    )


def downgrade() -> None:
    op.drop_table("ai_oauth_clients")
    op.drop_table("ai_oauth_codes")
    op.drop_index("ix_ai_tokens_connection_id", table_name="ai_tokens")
    op.drop_table("ai_tokens")
    op.drop_index("ix_ai_connections_user_id", table_name="ai_connections")
    op.drop_table("ai_connections")
