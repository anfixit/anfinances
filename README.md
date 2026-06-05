<div align="center">

# anfinances

**Self-hosted personal finance tracker** — multi-currency accounts, transactions & transfers, YNAB-style budgets, a recurring "plan-minimum", and dashboards. Built to own your data.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64)

[Русская версия →](README.ru.md)

</div>

---

## Overview

anfinances is a personal finance manager you run yourself. It tracks money across multiple accounts and currencies, plans monthly budgets in the envelope (YNAB) style with category groups and rollover, and shows where the money goes. No third-party services are required for the core to work — one `docker compose up` and it runs.

It started as a Google Sheets + Apps Script system, became a React + Node.js app, and is now a domain-driven FastAPI backend with a typed React frontend.

## Features

- **Accounts** — cards, cash, credit, savings, investment; per-account currency; manual ordering; soft-archive.
- **Transactions & transfers** — single entry point with an Expense / Income / Transfer switch. Cross-currency transfers reveal a "received" field and an optional fee — currency conversion without a separate mode.
- **Multi-currency** — global currency registry, per-user currency set, live rates from `open.er-api.com`, all balances rolled up to a base currency.
- **Budgets (YNAB-style)** — per month, grouped by parent category, collapsible. Budget a whole parent or individual subcategories. Progress bars, rollover, "copy from previous month".
- **Plan-minimum (recurring)** — fixed monthly obligations per category; auto-generate from spending history.
- **Dashboards** — net worth, monthly cashflow (income/expense), spending by category, with a month switcher.
- **Backup** — export transactions to CSV / XLSX, full backup to JSON, and one-click restore.
- **Themes** — warm light & dark, Material 3 Expressive design system.
- **Three auth modes** — `single_user`, `multi_user_no_verify`, `multi_user` via one env var.
- **Correctness-first** — money as `Decimal` end-to-end (`numeric(18,4)` in DB, string in JSON), soft-delete, fully typed.

## Screenshots

Drop your screenshots into [`docs/screenshots/`](docs/screenshots/) and they will render here.

| Dashboard | Budget | Transactions |
| --- | --- | --- |
| ![Dashboard](docs/screenshots/dashboard.png) | ![Budget](docs/screenshots/budget.png) | ![Transactions](docs/screenshots/transactions.png) |

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, FastAPI |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |
| Migrations | Alembic (async) |
| Validation | Pydantic v2 / pydantic-settings |
| Database | PostgreSQL 16 |
| Frontend | React 19, Vite, TypeScript (strict), TanStack Query, Recharts |
| Package managers | uv (backend), pnpm (frontend) |
| Tests / lint | pytest, ruff, mypy, ESLint |
| Deployment | Docker Compose, Nginx |

## Quick start (Docker)

Requirements: Docker + Docker Compose.

```bash
git clone https://github.com/<you>/anfinances.git
cd anfinances

cp backend/.env.example backend/.env
# Generate a secret and put it into backend/.env as SECRET_KEY=...
openssl rand -hex 32

docker compose up -d
```

Verify the backend:

```bash
curl http://localhost:8000/api/v1/health/live   # {"status":"ok"}
curl http://localhost:8000/api/v1/health/ready  # {"status":"ok","database":"ok"}
```

- API docs (OpenAPI): <http://localhost:8000/docs>
- For local frontend development, run Vite separately:

```bash
cd frontend
pnpm install
pnpm dev          # http://localhost:5173
```

In production the frontend is built (`pnpm build`) and served by Nginx — see [docs/deployment.md](docs/deployment.md).

## Configuration

All settings come from environment variables (`backend/.env`). Full reference: [docs/configuration.md](docs/configuration.md).

The most important one is the auth mode:

| `AUTH_MODE` | Use case |
| --- | --- |
| `single_user` | Self-host for one person. Registration disabled; the account is seeded from `SINGLE_USER_*`. |
| `multi_user_no_verify` | Open registration, no email verification (private hosting without SMTP). |
| `multi_user` | Open registration with email verification (public SaaS; requires `SMTP_*`). |

Money never trusts a hardcoded value — set `SECRET_KEY` (min 32 bytes) before first run.

## Architecture

The backend is domain-driven (`router → service → repository → model`), each domain in its own folder under `app/domains/`. The authoritative design document is [ARCHITECTURE.md](ARCHITECTURE.md).

```
anfinances/
├── backend/            # FastAPI + SQLAlchemy (async) + Alembic
│   └── app/
│       ├── core/       # config, db, middleware, exceptions, deps
│       └── domains/    # auth, accounts, categories, currencies,
│                       # transactions, budgets, recurring, summary,
│                       # export, import_, users
├── frontend/           # React + Vite + TypeScript
│   └── src/
│       ├── app/        # router, layout
│       ├── features/   # one folder per domain (api, hooks, pages)
│       └── lib/        # api client, query keys, helpers
├── docker-compose.yml
├── docker-compose.prod.yml
└── docs/
```

## Documentation

- [Configuration](docs/configuration.md) — every environment variable.
- [Development](docs/development.md) — local setup, tests, linting, coding standards.
- [Deployment](docs/deployment.md) — VPS, Docker Compose prod, Nginx, TLS.
- [Architecture](ARCHITECTURE.md) — design decisions.
- [Contributing](CONTRIBUTING.md) — how to propose changes.

## Roadmap

- [x] Backend (all domains) and frontend (dashboard, transactions, budgets, recurring, accounts, categories, currencies, settings, backup)
- [ ] List & restore archived accounts (`?include_archived`)
- [ ] Migration script: Google Sheets → PostgreSQL
- [ ] Google OAuth (v1.1)
- [ ] Tags, bank CSV parsers (v2.0)

## License

Licensed under the **GNU AGPL-3.0**. See [LICENSE](LICENSE).

AGPL is copyleft with a network clause: if you run a modified version as a network service, you must make your source available to its users. This keeps the project and any hosted derivatives open. For a different arrangement (e.g. a closed-source hosted offering), a separate commercial license would be required.
