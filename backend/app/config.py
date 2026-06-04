"""Конфигурация приложения через pydantic-settings.

Все настройки читаются из переменных окружения (или .env файла).
Никаких хардкодов — open-source first.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

AuthMode = Literal["single_user", "multi_user_no_verify", "multi_user"]


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
    postgres_password: str = "anfinances"
    postgres_db: str = "anfinances"

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> PostgresDsn:
        """Async URL для SQLAlchemy (драйвер asyncpg)."""
        return PostgresDsn.build(  # type: ignore[return-value]
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> PostgresDsn:
        """URL для Alembic (env.py работает в async-режиме)."""
        return PostgresDsn.build(  # type: ignore[return-value]
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    secret_key: SecretStr = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # Refresh-cookie: HttpOnly (ADR-024). secure=False — только для
    # локального http-dev; в проде на https — true.
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    argon2_time_cost: int = 2
    argon2_memory_cost: int = 65536

    password_min_length: int = 15
    password_max_length: int = 128
    password_min_zxcvbn_score: int = 3
    hibp_enabled: bool = True
    # Мягкий фейл: при недоступности HIBP не блокируем регистрацию.
    # Для публичного SaaS можно ужесточить (false).
    hibp_fail_open: bool = True
    hibp_timeout_seconds: float = 3.0

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


@lru_cache
def get_settings() -> Settings:
    """Возвращает singleton настроек.

    @lru_cache гарантирует один экземпляр на процесс: Settings
    создаётся один раз, .env читается один раз. В тестах можно
    переопределить через app.dependency_overrides.
    """
    return Settings()  # type: ignore[call-arg]
