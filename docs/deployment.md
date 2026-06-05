# Deployment

This describes a single-VPS deployment with Docker Compose and Nginx. The production overlay (`docker-compose.prod.yml`) adds Nginx, which terminates HTTP, proxies `/api/*` to the backend, and serves the built frontend from `frontend/dist`. PostgreSQL is not published outside the Docker network.

## 1. Prepare the server

- A VPS with Docker + Docker Compose.
- A domain name pointing (A record) to the server IP.
- Open ports 80 and 443.

## 2. Configure

```bash
git clone https://github.com/<you>/anfinances.git
cd anfinances
cp backend/.env.example backend/.env
```

Edit `backend/.env` for production:

```ini
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<strong-password>
CORS_ORIGINS=["https://your-domain.tld"]
COOKIE_SECURE=true
AUTH_MODE=single_user
SINGLE_USER_EMAIL=you@example.com
SINGLE_USER_PASSWORD=<set-once-then-can-be-removed>
HTTP_PORT=80
```

## 3. Build the frontend

```bash
cd frontend
pnpm install
pnpm build        # outputs to frontend/dist (served by Nginx)
cd ..
```

## 4. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
# seed the currency registry / defaults if applicable:
docker compose exec backend python scripts/seed.py
```

Verify:

```bash
curl https://your-domain.tld/api/v1/health/ready
```

## 5. HTTPS / TLS

The bundled `nginx/nginx.conf` serves HTTP and the SPA. To add TLS, terminate it at Nginx with a Let's Encrypt certificate. The common approaches:

- Run [Certbot](https://certbot.eff.org/) on the host (or as a sidecar), obtain a certificate for your domain, mount it into the Nginx container, and add a `443 ssl` server block that redirects `80 → 443`.
- Or front the stack with a TLS-terminating reverse proxy (Caddy, Traefik, or your provider's load balancer) and keep Nginx on plain HTTP behind it.

Make sure `COOKIE_SECURE=true` and `CORS_ORIGINS` use `https://` once TLS is on.

## 6. Backups

- **Application data**: use the in-app backup (Settings → Data → full JSON), or `GET /api/v1/export/all.json`.
- **Database**: schedule `pg_dump`:

```bash
docker compose exec -T postgres pg_dump -U anfinances anfinances > backup-$(date +%F).sql
```

## 7. Updates

```bash
git pull
cd frontend && pnpm install && pnpm build && cd ..
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
```

## Importing existing data

To bring data from the old Google Sheets system, use the backend migration script (`scripts/migrate_from_sheets.py`) or restore a JSON backup via Settings → Data → Restore (`POST /api/v1/import/all`).
