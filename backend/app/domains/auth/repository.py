"""Доступ к БД для домена auth.

Repository содержит только запросы, без бизнес-логики и без
commit — транзакцией управляет сервис (ADR-013).
"""

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import RefreshToken, User

__all__ = ["AuthRepository", "SqlAuthRepository"]


class AuthRepository(Protocol):
    """Интерфейс репозитория auth (для DI и тестов)."""

    async def get_user_by_email(self, email: str) -> User | None: ...

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None: ...

    async def add_user(self, user: User) -> User: ...

    async def add_refresh_token(self, token: RefreshToken) -> RefreshToken: ...

    async def get_refresh_token(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None: ...

    async def revoke_all_for_user(
        self, user_id: uuid.UUID, now: datetime
    ) -> None: ...

    async def delete_expired_tokens(self, now: datetime) -> None: ...


class SqlAuthRepository:
    """Реализация на SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def add_user(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def add_refresh_token(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_refresh_token(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash
        )
        if for_update:
            # Сериализуем конкурентные refresh одной сессии (на PG).
            # На SQLite молча игнорируется — для тестов безвредно.
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_all_for_user(
        self, user_id: uuid.UUID, now: datetime
    ) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )

    async def delete_expired_tokens(self, now: datetime) -> None:
        # Протухшие токены бесполезны (refresh всё равно проверяет
        # срок) — физически удаляем, чтобы таблица не росла. Отозванные,
        # но ещё не протухшие, оставляем: нужны для reuse-detection.
        await self._session.execute(
            delete(RefreshToken)
            .where(RefreshToken.expires_at < now)
            .execution_options(synchronize_session=False)
        )
