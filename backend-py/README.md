# anfinances-backend (Python)

Backend на FastAPI + PostgreSQL для anfinances. Версия v1.

> Старая Node.js + Google Sheets версия живёт в `../backend/` и пока работает параллельно.
> Полные архитектурные решения — в `../ARCHITECTURE.md` в корне репозитория.

## Быстрый старт через Docker (рекомендуется)

```bash
cd backend-py
cp .env.example .env
# Открой .env и установи SECRET_KEY:
#   openssl rand -hex 32
# Скопируй вывод в SECRET_KEY=...

cd ..  # docker-compose.yml лежит в корне проекта
docker compose up -d
```

Проверка что всё поднялось:

```bash
curl http://localhost:8000/api/v1/health/live
# → {"status": "ok"}

curl http://localhost:8000/api/v1/health/ready
# → {"status": "ok", "database": "ok"}
```

OpenAPI-документация: <http://localhost:8000/docs>

## Запуск без Docker

Нужен Python 3.13+ и [uv](https://docs.astral.sh/uv/).

```bash
cd backend-py

# Установка зависимостей в .venv
uv sync

# PostgreSQL должен быть подключаемым по адресу из .env (по умолчанию localhost:5432).
# Можно поднять только БД через compose:
docker compose up -d postgres

# Запуск API
uv run uvicorn app.main:app --reload
```

## Миграции

```bash
# Создать новую миграцию (после изменения моделей)
uv run alembic revision --autogenerate -m "описание изменения"

# Применить миграции
uv run alembic upgrade head

# Внутри Docker
docker compose exec backend alembic upgrade head
```

## Тесты

```bash
uv run pytest
```

## Структура

```
backend-py/
├── pyproject.toml           # зависимости, ruff, mypy, pytest
├── alembic.ini              # настройки Alembic
├── alembic/
│   ├── env.py               # async-конфигурация миграций
│   └── versions/            # сами миграции
├── docker/
│   └── Dockerfile           # multi-stage, через uv
├── scripts/                 # сиды, миграция из Sheets (заглушки на шаге 1)
├── tests/
└── app/
    ├── main.py              # FastAPI приложение
    ├── config.py            # настройки через pydantic-settings
    ├── database.py          # async engine + session factory
    ├── core/                # общая инфраструктура
    │   ├── dependencies.py  # FastAPI-зависимости (DbSession, SettingsDep)
    │   ├── exceptions.py    # кастомные исключения + единый формат ошибок
    │   ├── middleware.py    # CORS, request logging
    │   ├── pagination.py    # заглушка
    │   └── security.py      # заглушка (auth — шаг 3)
    └── domains/             # бизнес-домены (по фичам)
        ├── auth/            # шаг 3
        ├── accounts/        # шаг 4+
        ├── categories/
        ├── currencies/
        ├── transactions/
        ├── budgets/
        ├── recurring/
        ├── summary/
        ├── export/
        └── import_/
```

## Что сейчас работает

После `docker compose up -d`:

- ✅ PostgreSQL 16 в контейнере
- ✅ FastAPI поднимается, подключается к БД
- ✅ `/api/v1/health/live` и `/api/v1/health/ready`
- ✅ Alembic настроен и готов к первой миграции
- ✅ Логирование запросов с request-id
- ✅ Единый формат ошибок
- ✅ CORS из настроек

## Что НЕ работает (по плану)

- ❌ Модели данных — шаг 2
- ❌ Auth — шаг 3
- ❌ Все бизнес-домены — шаги 4+

## Production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

В prod добавляется nginx (терминирует HTTP, проксирует /api/* в backend,
раздаёт собранный фронтенд из `frontend/dist`). Postgres не публикуется наружу.
