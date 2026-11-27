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
    ValidationFailedError,
)
from app.core.password_policy import (
    PasswordPolicyError,
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

__all__ = ["AuthService", "RefreshReuseError"]

# Сколько после ротации старый refresh-токен ещё считается «второй
# вкладкой», а не кражей. Две вкладки (или восстановленная сессия
# браузера) шлют refresh одновременно с одной cookie; раньше вторая
# попадала в «повтор» и разлогинивала все устройства.
ROTATION_GRACE = timedelta(seconds=30)


class RefreshReuseError(UnauthorizedError):
    """Предъявлен давно ротированный или отозванный токен.

    Роут обязан сохранить отзыв всех сессий, хотя ответ — ошибка.
    """


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_DUMMY_HASH: str | None = None


def _dummy_hash(settings: Settings) -> str:
    """Хеш, который проверяют, когда пользователя нет.

    Без этого вход с несуществующим email отвечал на ~100 мс быстрее
    (Argon2 не считался), и по времени ответа можно было подобрать
    email владелицы.
    """
    global _DUMMY_HASH  # noqa: PLW0603 — ленивый кеш одного значения
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("no-such-user-padding", settings)
    return _DUMMY_HASH


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

        # Нарушение парольной политики — это ошибка ввода (422),
        # а не конфликт ресурса. Переводим в доменное исключение,
        # которое единый handler отдаст как VALIDATION_ERROR.
        try:
            validate_password(password, self._settings, user_inputs=[email])
        except PasswordPolicyError as exc:
            raise ValidationFailedError(str(exc)) from exc

        try:
            await self._pwned.assert_not_pwned(normalize_password(password))
        except PwnedError as exc:
            raise ValidationFailedError(str(exc)) from exc

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
        if user is None:
            # Та же работа, что при неверном пароле: время ответа не
            # должно выдавать, есть ли такой email.
            verify_password(
                _dummy_hash(self._settings),
                normalize_password(password),
                self._settings,
            )
            raise UnauthorizedError("Неверный email или пароль.")
        if not verify_password(
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

        stored = await self._repo.get_refresh_token(
            _hash_token(refresh_token), for_update=True
        )
        now = datetime.now(UTC)
        if stored is None:
            raise UnauthorizedError("Сессия недействительна.")
        expires_at = _aware(stored.expires_at)
        if expires_at <= now:
            raise UnauthorizedError("Сессия недействительна.")

        user = await self._repo.get_user_by_id(user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Пользователь недоступен.")

        if stored.revoked_at is not None:
            rotated_at = stored.rotated_at
            if (
                rotated_at is not None
                and now - _aware(rotated_at) <= ROTATION_GRACE
            ):
                # Только что ротирован — это параллельная вкладка с той
                # же cookie, а не кража: выдаём ей свою пару.
                return await self._issue_pair(user_id)
            # Давно ротированный или отозванный токен предъявлен
            # снова — классический признак кражи. Гасим все сессии.
            await self._revoke_everything(user, now)
            raise RefreshReuseError("Сессия недействительна.")

        stored.revoked_at = now
        stored.rotated_at = now
        return await self._issue_pair(user_id)

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> TokenPair:
        """Сменить пароль и завершить все остальные сессии.

        Возвращает новую пару для текущего устройства — чтобы человек,
        сменивший пароль, сам не вылетел.
        """
        if not verify_password(
            user.hashed_password,
            normalize_password(current_password),
            self._settings,
        ):
            raise ValidationFailedError("Текущий пароль указан неверно.")
        try:
            validate_password(
                new_password, self._settings, user_inputs=[user.email]
            )
        except PasswordPolicyError as exc:
            raise ValidationFailedError(str(exc)) from exc
        try:
            await self._pwned.assert_not_pwned(
                normalize_password(new_password)
            )
        except PwnedError as exc:
            raise ValidationFailedError(str(exc)) from exc

        user.hashed_password = hash_password(
            normalize_password(new_password), self._settings
        )
        await self._revoke_everything(user, datetime.now(UTC))
        return await self._issue_pair(user.id)

    async def logout_everywhere(self, user: User) -> None:
        """Завершить все сессии: и refresh-, и уже выданные access-токены."""
        await self._revoke_everything(user, datetime.now(UTC))

    async def _revoke_everything(self, user: User, now: datetime) -> None:
        await self._repo.revoke_all_for_user(user.id, now)
        user.sessions_revoked_at = now

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
        # Подчищаем протухшие токены, чтобы таблица не росла (S6).
        await self._repo.delete_expired_tokens(datetime.now(UTC))
        return TokenPair(access_token=access, refresh_token=refresh)


def _aware(moment: datetime) -> datetime:
    """SQLite в тестах отдаёт время без зоны; в базе всё в UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
