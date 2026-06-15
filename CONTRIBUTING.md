# Contributing to anfinances

Thanks for your interest! This guide covers how to set up the project and the conventions we follow. (Русский — ниже.)

## Getting started

See [docs/development.md](docs/development.md) for the full local setup. In short:

```bash
# Backend
cd backend && cp .env.example .env   # set SECRET_KEY (openssl rand -hex 32)
docker compose up -d postgres
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend
cd frontend && pnpm install && pnpm dev
```

## Before you open a pull request

Every change must pass the same gates we run locally:

```bash
# Backend
cd backend
uv run ruff check .
uv run mypy app
uv run pytest

# Frontend
cd frontend
pnpm tsc --noEmit
pnpm eslint .
```

Green `ruff`, `mypy`, `pytest`, `tsc`, and `eslint` are required.

## Coding standards

- The backend follows the project's Python coding standards (Clean Code / SOLID / DRY / YAGNI, full type hints, layered `router → service → repository → model`, money as `Decimal`). Keep business logic in services, DB access in repositories, and never touch the DB from a router.
- The frontend is TypeScript in strict mode. One folder per domain under `src/features/` (`api`, `hooks`, page components). Reuse the shared `api` client and query-key factory; no business logic in components.
- Soft-delete (`is_archived`) instead of hard deletes, except where the domain explicitly requires physical deletion.
- Money is a string in JSON, `Decimal` in Python, `numeric(18,4)` in the database.

## Commits & branches

- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` with an optional scope, e.g. `feat(budgets): rollover badge`.
- Branch from `main`, keep PRs focused, describe the change and how you tested it.
- Add or update tests for behavioural changes.

## Reporting issues

Open an issue with steps to reproduce, expected vs actual behaviour, and your environment (OS, Docker version, `AUTH_MODE`). For security-sensitive reports, please disclose privately rather than in a public issue.

---

## Контрибьютинг (кратко по-русски)

- Локальный запуск — в [docs/development.md](docs/development.md).
- Перед PR всё должно быть зелёным: `ruff`, `mypy`, `pytest` (бэкенд) и `pnpm tsc --noEmit`, `pnpm eslint .` (фронтенд).
- Бэкенд — по стандартам кода проекта: типизация, слои `router → service → repository → model`, деньги как `Decimal`, soft-delete.
- Фронтенд — TypeScript strict, домен = папка в `src/features/`, переиспользуй общий `api`-клиент и фабрику ключей запросов.
- Коммиты — Conventional Commits (`feat:`, `fix:`, `docs:` …), ветки от `main`, PR — сфокусированные, с описанием и способом проверки.
