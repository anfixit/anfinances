"""Бизнес-логика аутентификации.

register / login / refresh (с ротацией) / logout.
Не знает про HTTP. Зависит от AuthRepository (Protocol),
PwnedChecker (Protocol) и чистых функций security.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.core.exceptions import (
    AlreadyExistsError,
    UnauthorizedError,
)
from app.core.password_policy import (
    normalize_password,
    validate_password,
)
from app.core.pwned import PwnedChecker, PwnedError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.domains.auth.models import RefreshToken, User
from app.domains.auth.repository import AuthRepository
from app.domains.auth.schemas import TokenPair

__all__ = ["AuthService"]


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        settings: Settings,
        pwned: PwnedChecker,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._pwned = pwned

    async def register(
        self,
        email: str,
        password: str,
        name: str | None = None,
    ) -> tuple[User, TokenPair]:
        if await self._repo.get_user_by_email(email):
            raise AlreadyExistsError("Email уже зарегистрирован.")

        validate_password(password, self._settings, user_inputs=[email])
        try:
            await self._pwned.assert_not_pwned(normalize_password(password))
        except PwnedError as exc:
            raise AlreadyExistsError(str(exc)) from exc

        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(
                normalize_password(password), self._settings
            ),
        )
        await self._repo.add_user(user)
        tokens = await self._issue_pair(user.id)
        return user, tokens

    async def login(self, email: str, password: str) -> tuple[User, TokenPair]:
        user = await self._repo.get_user_by_email(email)
        if user is None or not verify_password(
            user.hashed_password,
            normalize_password(password),
            self._settings,
        ):
            raise UnauthorizedError("Неверный email или пароль.")
        if not user.is_active:
            raise UnauthorizedError("Учётная запись отключена.")

        tokens = await self._issue_pair(user.id)
        return user, tokens

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            user_id = decode_token(refresh_token, self._settings, "refresh")
        except TokenError as exc:
            raise UnauthorizedError("Невалидный токен.") from exc

        stored = await self._repo.get_refresh_token(_hash_token(refresh_token))
        now = datetime.now(UTC)
        if stored is None or stored.revoked_at is not None:
            raise UnauthorizedError("Сессия недействительна.")
        expires_at = stored.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise UnauthorizedError("Сессия недействительна.")

        stored.revoked_at = now
        return await self._issue_pair(user_id)

    async def logout(self, refresh_token: str) -> None:
        stored = await self._repo.get_refresh_token(_hash_token(refresh_token))
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)

    async def _issue_pair(self, user_id: uuid.UUID) -> TokenPair:
        access = create_access_token(user_id, self._settings)
        refresh = create_refresh_token(user_id, self._settings)
        expires_at = datetime.now(UTC) + timedelta(
            days=self._settings.refresh_token_expire_days
        )
        await self._repo.add_refresh_token(
            RefreshToken(
                user_id=user_id,
                token_hash=_hash_token(refresh),
                expires_at=expires_at,
            )
        )
        return TokenPair(access_token=access, refresh_token=refresh)
