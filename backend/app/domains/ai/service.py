"""Подключения ИИ: проверка токенов и личные токены.

Не знает про HTTP. OAuth-протокол живёт рядом, в oauth.py.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.domains.ai.models import (
    CONNECTION_PERSONAL,
    TOKEN_ACCESS,
    TOKEN_PERSONAL,
    AiConnection,
    AiToken,
)
from app.domains.ai.repository import AiRepository
from app.domains.ai.scopes import join_scopes, parse_scopes
from app.domains.ai.tokens import (
    ACCESS_PREFIX,
    PERSONAL_PREFIX,
    hash_secret,
    new_token,
)

__all__ = ["AiAccessService", "AiPrincipal", "aware"]

# last_used_at пишется не чаще раза в минуту: ассистент делает
# десятки запросов подряд, и каждый UPDATE ради точности до секунды
# был бы пустой нагрузкой.
_TOUCH_INTERVAL = timedelta(minutes=1)

_INVALID = "Токен недействителен."


def aware(value: datetime) -> datetime:
    """SQLite отдаёт даты без пояса; считаем их UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class AiPrincipal:
    """Кто пришёл с токеном ИИ и что ему можно."""

    connection_id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    name: str
    client_id: str | None
    scopes: tuple[str, ...]
    resource: str | None
    # Срок самого токена; у личного токена его нет.
    expires_at: datetime | None


class AiAccessService:
    def __init__(self, repo: AiRepository) -> None:
        self._repo = repo

    async def authenticate(self, raw: str, now: datetime) -> AiPrincipal:
        """Проверить Bearer-токен ИИ. Любая неудача — 401.

        Причину наружу не сообщаем: «отозван» и «не существует»
        для того, кто подбирает токены, должны выглядеть одинаково.
        """
        if raw.startswith(PERSONAL_PREFIX):
            expected_kind = TOKEN_PERSONAL
        elif raw.startswith(ACCESS_PREFIX):
            expected_kind = TOKEN_ACCESS
        else:
            raise UnauthorizedError(_INVALID)

        token = await self._repo.get_token(hash_secret(raw))
        if (
            token is None
            or token.kind != expected_kind
            or token.revoked_at is not None
        ):
            raise UnauthorizedError(_INVALID)
        if token.expires_at is not None and aware(token.expires_at) <= now:
            raise UnauthorizedError(_INVALID)

        conn = await self._repo.get_connection(token.connection_id)
        if conn is None or conn.revoked_at is not None:
            raise UnauthorizedError(_INVALID)

        return AiPrincipal(
            connection_id=conn.id,
            user_id=conn.user_id,
            kind=conn.kind,
            name=conn.name,
            client_id=conn.client_id,
            scopes=parse_scopes(conn.scopes),
            resource=conn.resource,
            expires_at=(aware(token.expires_at) if token.expires_at else None),
        )

    async def touch(self, connection_id: uuid.UUID, now: datetime) -> bool:
        """Отметить использование. True — что-то изменилось."""
        conn = await self._repo.get_connection(connection_id)
        if conn is None:
            return False
        last = conn.last_used_at
        if last is not None and now - aware(last) < _TOUCH_INTERVAL:
            return False
        conn.last_used_at = now
        return True

    async def list_connections(self, user_id: uuid.UUID) -> list[AiConnection]:
        return await self._repo.list_active_connections(user_id)

    async def create_personal_token(
        self,
        user_id: uuid.UUID,
        name: str,
        scopes: tuple[str, ...],
        resource: str,
    ) -> tuple[AiConnection, str]:
        """Личный токен: подключение и сам токен (показать один раз)."""
        conn = await self._repo.add_connection(
            AiConnection(
                user_id=user_id,
                kind=CONNECTION_PERSONAL,
                name=name,
                client_id=None,
                scopes=join_scopes(scopes),
                resource=resource,
            )
        )
        raw = new_token(PERSONAL_PREFIX)
        await self._repo.add_token(
            AiToken(
                connection_id=conn.id,
                kind=TOKEN_PERSONAL,
                token_hash=hash_secret(raw),
                expires_at=None,
            )
        )
        return conn, raw

    async def revoke(
        self, user_id: uuid.UUID, connection_id: uuid.UUID, now: datetime
    ) -> None:
        conn = await self._repo.get_connection(connection_id)
        # Чужое подключение неотличимо от несуществующего.
        if conn is None or conn.user_id != user_id:
            raise NotFoundError("Подключение не найдено.")
        if conn.revoked_at is None:
            conn.revoked_at = now
