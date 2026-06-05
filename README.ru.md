<div align="center">

# anfinances

**Self-hosted трекер личных финансов** — мультивалютные счета, операции и переводы, бюджеты в стиле YNAB, регулярный «план-минимум» и дашборды. Твои данные — у тебя.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64)

[English version →](README.md)

</div>

---

## О проекте

anfinances — менеджер личных финансов, который ты разворачиваешь сам. Учитывает деньги на нескольких счетах и в разных валютах, планирует месячный бюджет по «конвертному» (YNAB) принципу с группами категорий и переносом остатка, показывает, куда уходят деньги. Для базовой работы не нужны сторонние сервисы — один `docker compose up`, и оно работает.

Проект начинался как Google Sheets + Apps Script, затем стал приложением React + Node.js, а сейчас это domain-driven бэкенд на FastAPI и типизированный фронтенд на React.

## Возможности

- **Счета** — карты, наличные, кредитки, накопления, инвестиции; валюта на счёт; ручная сортировка; мягкая архивация.
- **Операции и переводы** — единая точка ввода с переключателем Расход / Доход / Перевод. При переводе между разными валютами появляется поле «получено» и опциональная комиссия — конвертация без отдельного режима.
- **Мультивалютность** — глобальный реестр валют, набор валют пользователя, курсы с `open.er-api.com`, все балансы сводятся к базовой валюте.
- **Бюджет (YNAB)** — помесячно, сгруппирован по родительским категориям, сворачивается. Лимит на весь родитель или на отдельные подкатегории. Прогресс-бары, перенос остатка, «скопировать из прошлого месяца».
- **План-минимум** — фиксированные ежемесячные обязательства по категориям; автогенерация из истории трат.
- **Дашборды** — капитал, помесячный cashflow (доход/расход), траты по категориям, с переключателем месяцев.
- **Бэкап** — экспорт операций в CSV / XLSX, полный бэкап в JSON и восстановление в один клик.
- **Темы** — тёплые светлая и тёмная, дизайн-система Material 3 Expressive.
- **Три режима авторизации** — `single_user`, `multi_user_no_verify`, `multi_user` одной переменной окружения.
- **Корректность прежде всего** — деньги как `Decimal` сквозь весь стек (`numeric(18,4)` в БД, строка в JSON), soft-delete, полная типизация.

## Скриншоты

Положи скриншоты в [`docs/screenshots/`](docs/screenshots/) — они отрисуются здесь.

| Дашборд | Бюджет | Операции |
| --- | --- | --- |
| ![Дашборд](docs/screenshots/dashboard.png) | ![Бюджет](docs/screenshots/budget.png) | ![Операции](docs/screenshots/transactions.png) |

## Стек

| Слой | Технология |
| --- | --- |
| Backend | Python 3.13, FastAPI |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| Миграции | Alembic (async) |
| Валидация | Pydantic v2 / pydantic-settings |
| База данных | PostgreSQL 16 |
| Frontend | React 19, Vite, TypeScript (strict), TanStack Query, Recharts |
| Пакетные менеджеры | uv (backend), pnpm (frontend) |
| Тесты / линт | pytest, ruff, mypy, ESLint |
| Деплой | Docker Compose, Nginx |

## Быстрый старт (Docker)

Нужно: Docker + Docker Compose.

```bash
git clone https://github.com/< you >/anfinances.git
cd anfinances

cp backend/.env.example backend/.env
# Сгенерируй секрет и впиши его в backend/.env как SECRET_KEY=...
openssl rand -hex 32

docker compose up -d
```

Проверка бэкенда:

```bash
curl http://localhost:8000/api/v1/health/live   # {"status":"ok"}
curl http://localhost:8000/api/v1/health/ready  # {"status":"ok","database":"ok"}
```

- API-документация (OpenAPI): <http://localhost:8000/docs>
- Для локальной разработки фронтенда запусти Vite отдельно:

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:5173
```

В продакшне фронтенд собирается (`pnpm build`) и раздаётся Nginx — см. [docs/deployment.md](docs/deployment.md).

## Конфигурация

Все настройки берутся из переменных окружения (`backend/.env`). Полный справочник: [docs/configuration.md](docs/configuration.md).

Главная из них — режим авторизации:

| `AUTH_MODE` | Когда использовать |
| --- | --- |
| `single_user` | Self-host на одного. Регистрация выключена, учётка задаётся через `SINGLE_USER_*`. |
| `multi_user_no_verify` | Открытая регистрация без верификации почты (свой хостинг без SMTP). |
| `multi_user` | Открытая регистрация с верификацией почты (публичный SaaS; нужен `SMTP_*`). |

Перед первым запуском обязательно задай `SECRET_KEY` (минимум 32 байта).

## Архитектура

Бэкенд построен по доменам (`router → service → repository → model`), каждый домен — в своей папке под `app/domains/`. Основной документ с решениями — [ARCHITECTURE.md](ARCHITECTURE.md).

```
anfinances/
├── backend/            # FastAPI + SQLAlchemy (async) + Alembic
│   └── app/
│       ├── core/       # конфиг, БД, middleware, исключения, зависимости
│       └── domains/    # auth, accounts, categories, currencies,
│                       # transactions, budgets, recurring, summary,
│                       # export, import_, users
├── frontend/           # React + Vite + TypeScript
│   └── src/
│       ├── app/        # роутер, layout
│       ├── features/   # по папке на домен (api, hooks, страницы)
│       └── lib/        # api-клиент, ключи запросов, утилиты
├── docker-compose.yml
├── docker-compose.prod.yml
└── docs/
```

## Документация

- [Конфигурация](docs/configuration.md) — все переменные окружения.
- [Разработка](docs/development.md) — локальный запуск, тесты, линт, стандарты кода.
- [Деплой](docs/deployment.md) — VPS, Docker Compose prod, Nginx, TLS.
- [Архитектура](ARCHITECTURE.md) — проектные решения.
- [Контрибьютинг](CONTRIBUTING.md) — как предлагать изменения.

## Дорожная карта

- [x] Бэкенд (все домены) и фронтенд (дашборд, операции, бюджет, план-минимум, счета, категории, валюты, настройки, бэкап)
- [ ] Просмотр и восстановление архивных счетов (`?include_archived`)
- [ ] Скрипт миграции: Google Sheets → PostgreSQL
- [ ] Google OAuth (v1.1)
- [ ] Теги, парсеры банковских CSV (v2.0)

## Лицензия

Распространяется под **GNU AGPL-3.0**. См. [LICENSE](LICENSE).

AGPL — это copyleft с сетевым условием: если ты запускаешь изменённую версию как сетевой сервис, ты обязан открыть исходники её пользователям. Так проект и любые размещённые производные остаются открытыми. Для иной схемы (например, закрытый хостинг) понадобится отдельная коммерческая лицензия.
