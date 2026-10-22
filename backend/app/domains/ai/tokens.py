"""Токены ИИ-интеграций: выпуск и хеширование.

Токены непрозрачные (случайная строка, а не JWT): их всё равно
проверяют по базе, чтобы отзыв действовал сразу, а подписанный
JWT пришлось бы ещё и держать в чёрном списке.

Префикс говорит, что это за токен, ещё до похода в базу — и
сканерам секретов, и get_current_user, который по нему отличает
токен ИИ от сессионного JWT сайта.
"""

import base64
import hashlib
import hmac
import secrets

__all__ = [
    "ACCESS_PREFIX",
    "AI_BEARER_PREFIXES",
    "PERSONAL_PREFIX",
    "REFRESH_PREFIX",
    "hash_secret",
    "is_ai_token",
    "new_code",
    "new_token",
    "pkce_matches",
]

PERSONAL_PREFIX = "anf_pat_"
ACCESS_PREFIX = "anf_oat_"
REFRESH_PREFIX = "anf_ort_"

# Чем можно авторизовать запрос к API. Refresh-токен сюда не входит:
# он годится только для обмена на новую пару.
AI_BEARER_PREFIXES: tuple[str, ...] = (PERSONAL_PREFIX, ACCESS_PREFIX)

# 32 байта энтропии → 43 символа base64url.
_TOKEN_BYTES = 32


def new_token(prefix: str) -> str:
    """Новый случайный токен с префиксом вида."""
    return prefix + secrets.token_urlsafe(_TOKEN_BYTES)


def new_code() -> str:
    """Новый код авторизации OAuth."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_secret(secret: str) -> str:
    """SHA-256 токена или кода: в базе хранится только он.

    Соль не нужна: секрет случайный и длинный, перебор по хешу
    бессмыслен, а детерминированный хеш позволяет искать по индексу.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def is_ai_token(token: str) -> bool:
    """Похоже ли значение Bearer на токен ИИ-интеграции."""
    return token.startswith(AI_BEARER_PREFIXES)


def pkce_matches(verifier: str, challenge: str) -> bool:
    """Проверка PKCE S256 со сравнением за постоянное время."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(expected, challenge)
