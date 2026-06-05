# Development

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (backend, Python 3.13+)
- Node.js 20+ and [pnpm](https://pnpm.io/) (frontend)

## Backend

```bash
cd backend
cp .env.example .env
# set SECRET_KEY:
openssl rand -hex 32   # paste into .env as SECRET_KEY=...

# Bring up PostgreSQL only (the rest runs on the host for hot reload)
docker compose up -d postgres

uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload     # http://localhost:8000
```

Health checks: `GET /api/v1/health/live`, `GET /api/v1/health/ready`. OpenAPI: `/docs`.

### Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
# inside Docker:
docker compose exec backend alembic upgrade head
```

### Tests, lint, types

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

## Frontend

```bash
cd frontend
pnpm install
pnpm dev            # http://localhost:5173 (proxies API to :8000)
```

### Checks

```bash
pnpm tsc --noEmit
pnpm eslint .
pnpm build          # production bundle into dist/
```

## Project layout

- Backend domains live in `backend/app/domains/<domain>/` as `models.py`, `schemas.py`, `repository.py`, `service.py`, `routes.py`.
- Frontend features live in `frontend/src/features/<domain>/` as `*Api.ts`, `hooks.ts`, `types.ts`, and page/component `.tsx`.
- Shared frontend infrastructure is in `frontend/src/lib/` (api client, query keys, formatters) and `frontend/src/app/` (router, layout).

## Conventions

- **Layers** (backend): `router → service → repository → model`. Business logic only in services; DB access only in repositories; routers manage the DB transaction (commit on success).
- **Types**: full type hints in Python; TypeScript in strict mode on the frontend.
- **Money**: `Decimal` in Python, `numeric(18,4)` in the DB, string in JSON.
- **Soft-delete**: `is_archived` instead of hard deletes (except where a domain requires physical deletion).
- **State/data fetching** (frontend): TanStack Query with a central query-key factory; mutations invalidate the relevant keys.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the PR checklist and commit conventions.
