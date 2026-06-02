"""Bootstrap единственного пользователя для режима single_user.

При старте, если AUTH_MODE=single_user и заданы SINGLE_USER_EMAIL
и SINGLE_USER_PASSWORD, создаёт этого пользователя, когда его ещё
нет. Идемпотентно: повторный запуск ничего не дублирует.

Пароль из .env намеренно НЕ проходит строгую политику и HIBP —
владелец self-host сам отвечает за него, и старт системы не должен
падать из-за «слабого» пароля.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.password_policy import normalize_password
from app.core.security import hash_password
from app.domains.auth.models import User
from app.domains.auth.repository import SqlAuthRepository

__all__ = ["bootstrap_single_user"]

logger = logging.getLogger("anfinances")


async def bootstrap_single_user(
    session: AsyncSession, settings: Settings
) -> None:
    """Создать single_user-аккаунт из .env, если его ещё нет."""
    if settings.auth_mode != "single_user":
        return

    email = settings.single_user_email
    password = settings.single_user_password
    if not email or password is None:
        logger.warning(
            "single_user режим, но SINGLE_USER_EMAIL/PASSWORD "
            "не заданы — пользователь не создан."
        )
        return

    repo = SqlAuthRepository(session)
    if await repo.get_user_by_email(email) is not None:
        return

    user = User(
        email=email,
        name=None,
        hashed_password=hash_password(
            normalize_password(password.get_secret_value()),
            settings,
        ),
        is_verified=True,
    )
    await repo.add_user(user)
    await session.commit()
    logger.info("Создан single_user-аккаунт: %s", email)
