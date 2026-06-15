# Configuration

All backend settings are read from environment variables (or `backend/.env`, copied from `backend/.env.example`). Settings are validated at startup by pydantic-settings — a missing or invalid required value fails fast with a clear error.

## Environment

| Variable | Default | Description |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `production` / `test`. |
| `DEBUG` | `true` | Verbose errors and FastAPI debug. Set `false` in production. |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |

## API

| Variable | Default | Description |
| --- | --- | --- |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON array of allowed origins. Set your real domain(s) in production. |

The API is served under `/api/v1`. OpenAPI docs are at `/docs`.

## Database

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | `postgres` inside Docker Compose (overridden automatically). |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_USER` | `anfinances` | |
| `POSTGRES_PASSWORD` | `anfinances` | Change in production. |
| `POSTGRES_DB` | `anfinances` | |
| `DB_POOL_SIZE` | `5` | SQLAlchemy pool size. |
| `DB_MAX_OVERFLOW` | `10` | |
| `DB_ECHO` | `false` | Log SQL to stdout. |

## Security

| Variable | Default | Description |
| --- | --- | --- |
| `SECRET_KEY` | — (required) | JWT signing key, min 32 bytes. Generate: `openssl rand -hex 32`. |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lives in an HttpOnly cookie. |
| `COOKIE_SECURE` | `true` | `false` only for local http dev; `true` on https. |
| `COOKIE_SAMESITE` | `lax` | `lax` / `strict` / `none`. |
| `PASSWORD_MIN_LENGTH` | `15` | |
| `HIBP_ENABLED` | `true` | Check passwords against Have-I-Been-Pwned. |
| `HIBP_FAIL_OPEN` | `true` | If HIBP is unreachable, don't block (set `false` for stricter public SaaS). |

## Auth mode

| Variable | Default | Description |
| --- | --- | --- |
| `AUTH_MODE` | `single_user` | `single_user` / `multi_user_no_verify` / `multi_user`. |
| `SINGLE_USER_EMAIL` | — | Seeded account email (only `single_user`). |
| `SINGLE_USER_PASSWORD` | — | Seeded account password (only `single_user`; needed once for setup). |

- **single_user** — registration disabled; the account is created from `SINGLE_USER_*` on startup if missing.
- **multi_user_no_verify** — open registration, no email verification (private hosting without SMTP).
- **multi_user** — open registration with email verification (public SaaS; requires `SMTP_*`).

## SMTP (only for `multi_user`)

| Variable | Default |
| --- | --- |
| `SMTP_HOST` | — |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | — |
| `SMTP_PASSWORD` | — |
| `SMTP_FROM_EMAIL` | — |

## Currencies

| Variable | Default | Description |
| --- | --- | --- |
| `EXCHANGE_RATE_API_URL` | `https://open.er-api.com/v6/latest` | Free, no key. |
| `EXCHANGE_RATE_API_KEY` | — | Optional, for a paid provider. |

## Docker

| Variable | Default | Description |
| --- | --- | --- |
| `BACKEND_PORT` | `8000` | Host port for the backend. |
| `HTTP_PORT` | `80` | Host port Nginx listens on (prod compose). |

## Frontend

The frontend reads its API base URL at build time. For production behind Nginx the API is same-origin under `/api/v1`, so no extra config is needed in the default setup. If you host the API on a different origin, set `VITE_API_BASE_URL` before `pnpm build`.
