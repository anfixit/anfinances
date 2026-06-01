"""Конфигурация приложения через pydantic-settings.

Все настройки читаются из переменных окружения (или .env файла).
Никаких хардкодов — open-source first.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Типы для AUTH_MODE. Реализация — в шаге 3, здесь только шаблон.
AuthMode = Literal["single_user", "multi_user_no_verify", "multi_user"]


class Settings(BaseSettings):
    """Главный объект настроек. Singleton через get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Окружение ──
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── API ──
    api_v1_prefix: str = "/api/v1"
    project_name: str = "anfinances"

    # CORS. В .env передаётся как JSON-массив или comma-separated.
    # Пример: CORS_ORIGINS=["http://localhost:5173"]
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # ── База данных ──
    # Раздельные поля + computed URL — так удобнее в docker-compose,
    # где хост/порт/имя БД задаются переменными отдельно.
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "anfinances"
    postgres_password: str = "anfinances"
    postgres_db: str = "anfinances"

    # Параметры пула SQLAlchemy.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False  # SQL-логирование. Для отладки. В prod — всегда False.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> PostgresDsn:
        """Async URL для SQLAlchemy (с asyncpg-драйвером)."""
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
        """Sync URL для Alembic (psycopg/psycopg2 не нужен — Alembic умеет async)."""
        return PostgresDsn.build(  # type: ignore[return-value]
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )

    # ── Security (используется с шага 3) ──
    # Минимум 32 байта. Сгенерировать: openssl rand -hex 32
    secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ── Auth-режим (шаблон, реализация в шаге 3) ──
    auth_mode: AuthMode = "single_user"

    # Для single_user-режима: учётка задаётся в .env, регистрация выключена.
    single_user_email: str | None = None
    single_user_password: str | None = None  # plain, при старте хешируется

    # Для multi_user-режима: настройки SMTP для верификации email.
    # На MVP можно не заполнять — реализация будет в v1.1.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    # ── Currencies ──
    # API для обновления курсов. По умолчанию — open.er-api.com (бесплатный, без ключа).
    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest"
    exchange_rate_api_key: str | None = None  # для платных провайдеров в будущем


@lru_cache
def get_settings() -> Settings:
    """Возвращает singleton настроек.

    @lru_cache гарантирует один экземпляр на процесс — Settings создаётся
    один раз, .env читается один раз. В тестах можно переопределить
    через app.dependency_overrides.
    """
    return Settings()  # type: ignore[call-arg]
