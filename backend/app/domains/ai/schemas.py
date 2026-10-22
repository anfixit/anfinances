"""Pydantic-схемы домена ai (кроме OAuth-протокола: там свой формат)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domains.ai.models import AiConnection
from app.domains.ai.scopes import parse_scopes

__all__ = [
    "AiConnectionRead",
    "AiWhoAmI",
    "AuthorizeApprove",
    "AuthorizeCheck",
    "AuthorizeRedirect",
    "PersonalTokenCreate",
    "PersonalTokenCreated",
]

Scope = Literal["finance.read", "finance.write"]


class AiConnectionRead(BaseModel):
    """Подключение в списке на странице настроек.

    Без токенов и их хешей: показать заново токен нельзя.
    """

    id: uuid.UUID
    kind: Literal["personal", "oauth"]
    name: str
    client_id: str | None
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None

    @classmethod
    def from_model(cls, conn: AiConnection) -> "AiConnectionRead":
        return cls(
            id=conn.id,
            kind="oauth" if conn.kind == "oauth" else "personal",
            name=conn.name,
            client_id=conn.client_id,
            scopes=list(parse_scopes(conn.scopes)),
            created_at=conn.created_at,
            last_used_at=conn.last_used_at,
        )


class PersonalTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    scopes: list[Scope] = Field(min_length=1)


class PersonalTokenCreated(BaseModel):
    connection: AiConnectionRead
    # Показывается один раз: в базе остаётся только хеш.
    token: str


class AiWhoAmI(BaseModel):
    """Ответ /ai/whoami — для MCP-сервера, проверяющего токен."""

    connection_id: uuid.UUID
    user_id: uuid.UUID
    scopes: list[str]
    kind: Literal["personal", "oauth"]
    name: str
    client_id: str | None
    resource: str | None
    expires_at: datetime | None
    # Чтобы MCP-серверу не ходить ещё и в /auth/me за каждым ответом.
    timezone: str
    default_currency: str


class AuthorizeCheck(BaseModel):
    """Итог проверки запроса авторизации для страницы согласия.

    ``status=ok`` — показать согласие: кто просит и какие права.
    ``status=error`` — показать ``message``; если есть
    ``redirect_to``, ошибку можно вернуть приложению.
    """

    status: Literal["ok", "error"]
    client_id: str | None = None
    client_name: str | None = None
    # Куда уйдёт код — чтобы имя приложения нельзя было подделать
    # незаметно для пользователя.
    redirect_host: str | None = None
    scopes: list[str] = Field(default_factory=list)
    deny_redirect_to: str | None = None
    error: str | None = None
    message: str | None = None
    redirect_to: str | None = None


class AuthorizeApprove(BaseModel):
    """«Разрешить»: исходный запрос авторизации и выбранные права."""

    model_config = ConfigDict(extra="forbid")

    response_type: str | None = None
    client_id: str | None = None
    redirect_uri: str | None = None
    scope: str | None = None
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    resource: str | None = None
    scopes: list[Scope] = Field(min_length=1)


class AuthorizeRedirect(BaseModel):
    redirect_to: str
