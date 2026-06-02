"""Alembic environment — async версия.

Берёт URL базы и Base.metadata из app.* (а не из alembic.ini), чтобы все
настройки шли через .env, и миграции автоматически видели все модели.

Когда появятся модели в app/domains/*/models.py — импортировать их здесь,
чтобы Alembic знал о них для autogenerate (см. блок IMPORT_MODELS ниже).
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import get_settings
from app.database import Base

# ── Конфиг Alembic ───────────────────────────────────────────────────

config = context.config

# Логирование из alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Перезаписываем URL значением из .env (через pydantic-settings).
settings = get_settings()
config.set_main_option("sqlalchemy.url", str(settings.database_url))


# ── IMPORT_MODELS ────────────────────────────────────────────────────
# Когда в шаге 2 появятся модели — импортировать их здесь, чтобы Alembic
# видел их при autogenerate. Пример:
#
# from app.domains.auth.models import User, RefreshToken  # noqa: F401
# from app.domains.accounts.models import Account  # noqa: F401
# from app.domains.categories.models import Category  # noqa: F401
# from app.domains.currencies.models import Currency, ExchangeRate  # noqa: F401
# from app.domains.transactions.models import Transaction, Transfer  # noqa: F401
# from app.domains.budgets.models import Budget  # noqa: F401
# from app.domains.recurring.models import RecurringExpense  # noqa: F401

target_metadata = Base.metadata


# ── Offline / online ─────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Миграции в "offline" режиме — генерируют SQL без подключения к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # детектировать смену типа колонки
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Создаёт async engine, открывает соединение и запускает миграции."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Точка входа для online-режима (с подключением к БД)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
