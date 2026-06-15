# Deployment

Single-VPS deployment with Docker Compose, Nginx, and Let's Encrypt (Certbot). The production overlay (`docker-compose.prod.yml`) runs Nginx (terminates HTTPS, proxies `/api/*` to the backend, serves the built frontend from `frontend/dist`), a Certbot sidecar (issues and auto-renews the TLS certificate), and PostgreSQL (not published outside the Docker network).

## 1. Prepare the server

- A VPS with Docker + Docker Compose.
- A domain with an A record pointing to the server IP.
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

Set your domain in the Nginx config (replaces all 4 occurrences):

```bash
sed -i 's/your-domain.tld/anfinances.example.com/g' nginx/nginx.conf
```

## 3. Build the frontend

```bash
cd frontend && pnpm install && pnpm build && cd ..   # → frontend/dist
```

## 4. Issue the TLS certificate (first time only)

The bootstrap script puts a temporary self-signed cert in place so Nginx can start, then obtains a real Let's Encrypt certificate over the ACME HTTP challenge:

```bash
chmod +x scripts/init-letsencrypt.sh
DOMAIN=anfinances.example.com EMAIL=you@example.com ./scripts/init-letsencrypt.sh
# Test run against LE staging first (avoids rate limits): prepend STAGING=1
```

## 5. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed.py   # currencies / defaults
```

Verify:

```bash
curl https://anfinances.example.com/api/v1/health/ready
```

Renewal is automatic: the `certbot` service renews every 12h and Nginx reloads every 6h to pick up new certificates.

## 6. Backups

- **Application data**: in-app backup (Settings → Data → full JSON), or `GET /api/v1/export/all.json`.
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

## Simpler alternative: Caddy

If you prefer zero-config HTTPS, front the stack with [Caddy](https://caddyserver.com/) instead of Nginx + Certbot — it provisions and renews certificates automatically from just a domain and email. The trade-off is replacing the Nginx config with a `Caddyfile`; the rest of the stack is unchanged.

## Importing existing data

To restore data, use a JSON backup via Settings → Data → Restore (`POST /api/v1/import/all`).
