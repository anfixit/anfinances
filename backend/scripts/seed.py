"""Сид/обновление справочных данных: курсы валют.

Дефолтные категории и аккаунт single_user создаёт bootstrap при
старте приложения; курсы валют также обновляются в lifespan. Этот
скрипт — для ручного запуска того же обновления (идемпотентно):

    docker compose exec backend python -m scripts.seed

Полезно, если приложение поднялось, пока внешний провайдер курсов
был недоступен, и нужно обновить курсы, не перезапуская контейнер.
"""

import asyncio
import logging

from app.config import get_settings
from app.database import create_db_engine, create_sessionmaker
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService

logger = logging.getLogger("anfinances")


async def _seed() -> None:
    settings = get_settings()
    # Движок собирается так же, как в приложении: глобальной фабрики
    # сессий в app.database нет с тех пор, как engine переехал в
    # lifespan, и скрипт падал на импорте.
    engine = create_db_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            service = CurrencyService(
                SqlCurrencyRepository(session),
                ErApiRatesProvider(settings),
            )
            await service.refresh_rates()
            await session.commit()
    finally:
        await engine.dispose()
    logger.info("Курсы валют обновлены.")


def main() -> None:
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
