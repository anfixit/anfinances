"""Модели ИИ-интеграций: подключения, токены, коды OAuth, клиенты.

Подключение — единица доступа, которую пользователь видит и может
отозвать: одно на каждое OAuth-разрешение и одно на каждый личный
токен. Токены ссылаются на подключение, поэтому отзыв подключения
разом гасит и access-, и refresh-токены.

Сами токены в базе не лежат — только SHA-256. Утечка дампа не даёт
ничего: токен случайный, подобрать его по хешу нельзя.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin

# Значения kind строками, а не enum'ом PostgreSQL: набор маленький
# и закрытый, а лишний тип в базе — лишняя миграция при каждом
# новом виде.
CONNECTION_PERSONAL = "personal"
CONNECTION_OAUTH = "oauth"

# Названия видов токенов, а не сами токены — отсюда noqa на S105.
TOKEN_PERSONAL = "personal"  # noqa: S105
TOKEN_ACCESS = "access"  # noqa: S105
TOKEN_REFRESH = "refresh"  # noqa: S105


class AiConnection(UUIDMixin, Base):
    """Одно разрешение доступа для ИИ-ассистента."""

    __tablename__ = "ai_connections"
    __table_args__ = (Index("ix_ai_connections_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Имя клиента (OAuth) или то, что пользователь ввёл (личный токен).
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(2000))
    # Через пробел, как в OAuth: «finance.read finance.write».
    scopes: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AiToken(UUIDMixin, Base):
    """Токен подключения: личный, access или refresh.

    Отозванный refresh не удаляется до своего срока: если его
    предъявят ещё раз, это признак кражи, и подключение отзывается
    целиком.
    """

    __tablename__ = "ai_tokens"
    __table_args__ = (Index("ix_ai_tokens_connection_id", "connection_id"),)

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    # У личного токена срока нет: он живёт до отзыва.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AiAuthCode(UUIDMixin, Base):
    """Код авторизации OAuth: одноразовый, живёт пять минут.

    Привязан ко всему, что пользователь одобрил: клиенту, адресу
    возврата, PKCE-challenge, правам и ресурсу. Обмен проверяет
    каждое из этих полей.
    """

    __tablename__ = "ai_oauth_codes"

    code_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(2000), nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(2000), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    scopes: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str] = mapped_column(String(2000), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Какое подключение родилось из кода: повторный обмен его отзывает.
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_connections.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AiOAuthClient(UUIDMixin, Base):
    """Клиент, зарегистрированный динамически (RFC 7591)."""

    __tablename__ = "ai_oauth_clients"

    client_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    redirect_uris: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
