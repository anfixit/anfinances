"""Доступ к БД для домена ai.

Только запросы, без бизнес-логики и без commit — транзакцией
управляет роут (ADR-013).
"""

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ai.models import (
    AiAuthCode,
    AiConnection,
    AiOAuthClient,
    AiToken,
)

__all__ = ["AiRepository", "SqlAiRepository"]


class AiRepository(Protocol):
    async def add_connection(self, conn: AiConnection) -> AiConnection: ...

    async def get_connection(
        self, connection_id: uuid.UUID
    ) -> AiConnection | None: ...

    async def list_active_connections(
        self, user_id: uuid.UUID
    ) -> list[AiConnection]: ...

    async def revoke_connection(
        self, connection_id: uuid.UUID, now: datetime
    ) -> None: ...

    async def add_token(self, token: AiToken) -> AiToken: ...

    async def get_token(
        self, token_hash: str, *, for_update: bool = False
    ) -> AiToken | None: ...

    async def add_code(self, code: AiAuthCode) -> AiAuthCode: ...

    async def get_code(
        self, code_hash: str, *, for_update: bool = False
    ) -> AiAuthCode | None: ...

    async def add_client(self, client: AiOAuthClient) -> AiOAuthClient: ...

    async def get_client(self, client_id: str) -> AiOAuthClient | None: ...

    async def delete_expired(self, now: datetime) -> None: ...


class SqlAiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_connection(self, conn: AiConnection) -> AiConnection:
        self._session.add(conn)
        await self._session.flush()
        return conn

    async def get_connection(
        self, connection_id: uuid.UUID
    ) -> AiConnection | None:
        return await self._session.get(AiConnection, connection_id)

    async def list_active_connections(
        self, user_id: uuid.UUID
    ) -> list[AiConnection]:
        result = await self._session.execute(
            select(AiConnection)
            .where(
                AiConnection.user_id == user_id,
                AiConnection.revoked_at.is_(None),
            )
            .order_by(AiConnection.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_connection(
        self, connection_id: uuid.UUID, now: datetime
    ) -> None:
        await self._session.execute(
            update(AiConnection)
            .where(
                AiConnection.id == connection_id,
                AiConnection.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session="fetch")
        )

    async def add_token(self, token: AiToken) -> AiToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_token(
        self, token_hash: str, *, for_update: bool = False
    ) -> AiToken | None:
        stmt = select(AiToken).where(AiToken.token_hash == token_hash)
        if for_update:
            # Два одновременных refresh одним токеном не должны оба
            # получить новую пару. На SQLite игнорируется.
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_code(self, code: AiAuthCode) -> AiAuthCode:
        self._session.add(code)
        await self._session.flush()
        return code

    async def get_code(
        self, code_hash: str, *, for_update: bool = False
    ) -> AiAuthCode | None:
        stmt = select(AiAuthCode).where(AiAuthCode.code_hash == code_hash)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_client(self, client: AiOAuthClient) -> AiOAuthClient:
        self._session.add(client)
        await self._session.flush()
        return client

    async def get_client(self, client_id: str) -> AiOAuthClient | None:
        result = await self._session.execute(
            select(AiOAuthClient).where(AiOAuthClient.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def delete_expired(self, now: datetime) -> None:
        # Протухшие коды и токены уже ничего не открывают — удаляем,
        # чтобы таблицы не росли. Отозванный, но живой refresh
        # остаётся: по нему ловится повторное предъявление.
        await self._session.execute(
            delete(AiAuthCode)
            .where(AiAuthCode.expires_at < now)
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(
            delete(AiToken)
            .where(AiToken.expires_at < now)
            .execution_options(synchronize_session=False)
        )
