"""Проверка качества паролей по NIST SP 800-63B Rev.4.

Композиционные правила (заглавная/цифра/символ) сознательно НЕ
применяются — Rev.4 их запрещает. Вместо них: длина, нормализация
Unicode, оценка стойкости zxcvbn и локальный блоклист утёкших.
Проверка по онлайн-базе HIBP вынесена отдельно (pwned.py), т.к.
требует сети и должна подменяться в тестах.
"""

import unicodedata

from zxcvbn import zxcvbn

from app.config import Settings

__all__ = [
    "PasswordPolicyError",
    "normalize_password",
    "validate_password",
]


class PasswordPolicyError(Exception):
    """Пароль не удовлетворяет политике."""


_LOCAL_BLOCKLIST: frozenset[str] = frozenset(
    {
        "correcthorsebatterystaple",
        "correct horse battery staple",
        "thequickbrownfoxjumpsoverthelazydog",
        "administratoradministrator",
        "passwordpassword",
        "password12345678",
        "qwertyuiopasdfgh",
        "123456789012345",
        "letmeinletmein12",
    }
)


def normalize_password(plain: str) -> str:
    """Нормализовать Unicode (NFKC) для стабильного хеширования.

    Без нормализации визуально одинаковые пассфразы с разными
    кодовыми точками дали бы разные хеши.
    """
    return unicodedata.normalize("NFKC", plain)


def validate_password(
    plain: str,
    settings: Settings,
    user_inputs: list[str] | None = None,
) -> None:
    """Проверить пароль офлайн-правилами политики.

    Args:
        plain: пароль как ввёл пользователь (до нормализации).
        settings: настройки с порогами политики.
        user_inputs: email, имя и пр. — zxcvbn штрафует пароли,
            похожие на эти данные.

    Raises:
        PasswordPolicyError: при нарушении длины, попадании в
            блоклист или недостаточном score zxcvbn.
    """
    normalized = normalize_password(plain)

    length = len(normalized)
    if length < settings.password_min_length:
        raise PasswordPolicyError(
            f"Пароль должен быть не короче "
            f"{settings.password_min_length} символов."
        )
    if length > settings.password_max_length:
        raise PasswordPolicyError(
            f"Пароль должен быть не длиннее "
            f"{settings.password_max_length} символов."
        )

    if normalized.casefold() in _LOCAL_BLOCKLIST:
        raise PasswordPolicyError(
            "Этот пароль слишком известен. Выберите другой."
        )

    result = zxcvbn(normalized, user_inputs=user_inputs or [])
    if result["score"] < settings.password_min_zxcvbn_score:
        suggestions = result["feedback"].get("suggestions") or []
        hint = f" {suggestions[0]}" if suggestions else ""
        raise PasswordPolicyError(f"Пароль слишком слабый.{hint}")
