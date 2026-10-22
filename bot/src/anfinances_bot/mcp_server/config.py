"""Настройки MCP-сервера — отдельно от настроек бота.

Сервер живёт в том же образе, что и бот, но секретов бота ему не
нужно: ни токена телеграма, ни ключей моделей, ни пароля владелицы.
Каждый запрос приходит со своим токеном, и в сайт сервер ходит
только с ним. Поэтому настройки свои, и все поля с умолчаниями —
контейнер поднимается на пустом окружении.
"""

from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from anfinances_bot.config import parse_default_accounts

__all__ = ["READ_SCOPE", "WRITE_SCOPE", "McpSettings", "get_mcp_settings"]

READ_SCOPE = "finance.read"
# Запись включает чтение: токен с одним finance.write читает тоже.
WRITE_SCOPE = "finance.write"


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Внутри compose-сети сайт доступен по имени сервиса.
    anfinances_base_url: str = "http://backend:8000/api/v1"
    # Адрес, который пользователь вводит в ChatGPT или Claude. Он же
    # resource в метаданных: клиенты сверяют их строкой, поэтому без
    # завершающего слэша и ровно в том виде, как его вводят.
    mcp_public_url: str = "https://anfinances.ru/mcp"
    # Издатель токенов. Тоже сверяется строкой с issuer в метаданных
    # сервера авторизации — лишний слэш ломает вход в ChatGPT.
    mcp_issuer: str = "https://anfinances.ru"

    # Слушаем все интерфейсы контейнера: наружу порт не публикуется,
    # до сервера доходит только Caddy по внутренней сети.
    mcp_host: str = "0.0.0.0"  # noqa: S104
    mcp_port: int = Field(default=8100, ge=1, le=65535)

    # Часовой пояс на случай, если профиль по токену не прочитать.
    # Совпадает с умолчанием профиля на сайте.
    mcp_timezone: str = "Europe/Moscow"
    # Те же умолчания по валютам, что у бота. Не обязательны: без них
    # трата без названного счёта просто вернёт вопрос, какой счёт.
    bot_default_accounts: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict
    )
    # Откуда разрешён заголовок Origin. Клиенты ChatGPT и Claude
    # ходят со своих серверов, а браузерная страница с чужого сайта
    # к финансам ходить не должна.
    mcp_allowed_origins: Annotated[tuple[str, ...], NoDecode] = (
        "https://anfinances.ru",
        "https://chatgpt.com",
        "https://claude.ai",
    )

    @field_validator("bot_default_accounts", mode="before")
    @classmethod
    def _parse_default_accounts(cls, value: object) -> object:
        return parse_default_accounts(value)

    @field_validator("mcp_allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """Принять "https://a.ru,https://b.ru"."""
        if not isinstance(value, str):
            return value
        return tuple(p.strip() for p in value.split(",") if p.strip())

    @field_validator("mcp_public_url", "mcp_issuer")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        """Без завершающего слэша: сверка идёт строкой, не как URL."""
        return value.rstrip("/")

    @property
    def resource_metadata_url(self) -> str:
        """Адрес метаданных ресурса по RFC 9728, раздел 3.1.

        ``/.well-known/oauth-protected-resource`` встаёт между хостом
        и путём ресурса: для ``https://anfinances.ru/mcp`` это
        ``https://anfinances.ru/.well-known/oauth-protected-resource/mcp``.
        """
        parts = urlsplit(self.mcp_public_url)
        return (
            f"{parts.scheme}://{parts.netloc}"
            f"/.well-known/oauth-protected-resource{parts.path}"
        )

    @property
    def public_host(self) -> str:
        return urlsplit(self.mcp_public_url).netloc


@lru_cache
def get_mcp_settings() -> McpSettings:
    return McpSettings()
