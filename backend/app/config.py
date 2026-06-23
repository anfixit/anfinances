"""Конфигурация приложения через pydantic-settings.

Все настройки читаются из переменных окружения (или .env файла).
Никаких хардкодов — open-source first.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import (
    Field,
    PostgresDsn,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

AuthMode = Literal["single_user", "multi_user_no_verify", "multi_user"]

# Значения-заглушки из .env.example: в проде их быть не должно.
# Это эталоны для сравнения, а не секреты — отсюда noqa на S105.
_PLACEHOLDER_SECRET = "change-me-use-openssl-rand-hex-32-to-generate"  # noqa: S105
_DEFAULT_DB_PASSWORD = "anfinances"  # noqa: S105


class Settings(BaseSettings):
    """Главный объект настроек. Singleton через get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    api_v1_prefix: str = "/api/v1"
    project_name: str = "anfinances"

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "anfinances"
    postgres_password: SecretStr = SecretStr("anfinances")
    postgres_db: str = "anfinances"

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    @property
    def database_url(self) -> PostgresDsn:
        """Async URL для SQLAlchemy (драйвер asyncpg)."""
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    secret_key: SecretStr = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    argon2_time_cost: int = 2
    argon2_memory_cost: int = 65536

    password_min_length: int = 15
    password_max_length: int = 128
    password_min_zxcvbn_score: int = 3
    hibp_enabled: bool = True
    hibp_fail_open: bool = True
    hibp_timeout_seconds: float = 3.0

    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/minute"

    auth_mode: AuthMode = "single_user"

    single_user_email: str | None = None
    single_user_password: SecretStr | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None

    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest"
    exchange_rate_api_key: str | None = None
    exchange_rate_timeout_seconds: float = 10.0

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Self:
        """В production громко падаем на небезопасной конфигурации.

        Лучше не подняться, чем тихо работать с debug-режимом, cookie
        без Secure, дефолтным секретом/паролем или (для single_user)
        без учётных данных — тогда войти было бы некем и нельзя.
        """
        if self.environment != "production":
            return self

        problems: list[str] = []

        if self.debug:
            problems.append("DEBUG должен быть false")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE должен быть true (нужен HTTPS)")
        if self.secret_key.get_secret_value() == _PLACEHOLDER_SECRET:
            problems.append(
                "SECRET_KEY не сгенерирован (openssl rand -hex 32)"
            )
        if self.postgres_password.get_secret_value() == _DEFAULT_DB_PASSWORD:
            problems.append("POSTGRES_PASSWORD не должен быть дефолтным")
        if self.auth_mode == "single_user" and (
            not self.single_user_email or self.single_user_password is None
        ):
            problems.append(
                "single_user требует SINGLE_USER_EMAIL и SINGLE_USER_PASSWORD"
            )

        if problems:
            raise ValueError(
                "Небезопасная production-конфигурация: " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Возвращает singleton настроек."""
    return Settings()
