"""Настройки бота — только из переменных окружения.

Секреты в код не попадают никогда: всё приходит из .env, который
деплой раскладывает из GitHub Secrets.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

__all__ = ["BotSettings", "get_bot_settings"]


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: SecretStr
    # NoDecode: иначе pydantic-settings разберёт значение как JSON
    # ещё до валидаторов, и "111, 222" в него не уложится.
    telegram_allowed_user_ids: Annotated[frozenset[int], NoDecode]

    anthropic_api_key: SecretStr
    openai_api_key: SecretStr
    speech_model: str = "whisper-1"

    # Внутри compose-сети сайт доступен по имени сервиса; наружу
    # бот не ходит и о публичном адресе ничего не знает.
    anfinances_base_url: str = "http://backend:8000/api/v1"
    single_user_email: str
    single_user_password: SecretStr

    # Умолчания по валютам: "RUB=Альфа,UZS=Uzcard Капитал".
    # Одного счёта на всё не хватает — у владельца три валюты, и
    # рублёвое умолчание не помогло бы ни сумам, ни долларам.
    bot_default_accounts: Annotated[dict[str, str], NoDecode]
    # NoDecode по той же причине, что и у списка ID выше.
    bot_quiet_hours: Annotated[tuple[int, int], NoDecode] = (23, 9)
    # 29–31 есть не в каждом месяце: совещание бы пропускалось.
    bot_budget_meeting_day: int = Field(default=1, ge=1, le=28)

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> object:
        """Принять "111, 222" — так удобнее держать в секрете."""
        if not isinstance(value, str):
            return value
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return frozenset(int(p) for p in parts)

    @field_validator("telegram_allowed_user_ids")
    @classmethod
    def _reject_empty(cls, value: frozenset[int]) -> frozenset[int]:
        """Пустой список открыл бы финансы любому, кто найдёт бота."""
        if not value:
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS не может быть пустым.")
        return value

    @field_validator("bot_default_accounts", mode="before")
    @classmethod
    def _parse_default_accounts(cls, value: object) -> object:
        """Принять "RUB=Альфа,UZS=Uzcard Капитал"."""
        if not isinstance(value, str):
            return value
        parsed: dict[str, str] = {}
        for chunk in value.split(","):
            if not chunk.strip():
                continue
            if "=" not in chunk:
                raise ValueError(
                    "BOT_DEFAULT_ACCOUNTS должен быть вида "
                    "RUB=Альфа,UZS=Uzcard Капитал."
                )
            code, name = chunk.split("=", 1)
            parsed[code.strip().upper()] = name.strip()
        return parsed

    @field_validator("bot_default_accounts")
    @classmethod
    def _reject_empty_defaults(cls, value: dict[str, str]) -> dict[str, str]:
        """Без умолчаний бот переспрашивал бы счёт на каждой трате."""
        if not value:
            raise ValueError("BOT_DEFAULT_ACCOUNTS не может быть пустым.")
        return value

    @field_validator("bot_quiet_hours", mode="before")
    @classmethod
    def _parse_quiet_hours(cls, value: object) -> object:
        """Принять "23-9" — час начала и час конца тишины."""
        if not isinstance(value, str):
            return value
        try:
            start_s, end_s = value.split("-")
            start, end = int(start_s), int(end_s)
        except ValueError as exc:
            raise ValueError("BOT_QUIET_HOURS должен быть вида 23-9.") from exc
        if not (0 <= start <= 23 and 0 <= end <= 23):
            raise ValueError("Часы тишины должны быть в диапазоне 0..23.")
        return (start, end)


@lru_cache
def get_bot_settings() -> BotSettings:
    return BotSettings()
