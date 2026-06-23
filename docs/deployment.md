# Deployment

Production runs on a single server via Docker Compose. Images are
built in CI and pushed to GitHub Container Registry (GHCR); the server
only pulls and runs them — nothing is built on the server. TLS is
handled by **Caddy** at the edge: it obtains and auto-renews a Let's
Encrypt certificate from just your domain and email.

Topology:

```
caddy (80/443, auto-TLS)
  └─ frontend (nginx: serves the SPA, proxies /api/* to the backend,
     rate-limits /auth/*)
       └─ backend (FastAPI/uvicorn)
            └─ postgres (not published outside the Docker network)
```

The compose file for this is `docker-compose.deploy.yml`. The older
Nginx + Certbot overlay (`docker-compose.prod.yml`,
`scripts/init-letsencrypt.sh`) is superseded by this Caddy setup and
kept only for reference.

## 1. Prerequisites

- A server with Docker + the Compose plugin.
- A domain with an A record pointing to the server IP.
- Ports **80** and **443** open (Caddy needs 80 for the ACME challenge).

One-time server preparation:

```bash
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # re-login afterwards
git clone https://github.com/<you>/anfinances.git /opt/anfinances
```

## 2. Set your domain

In the cloned repo, replace the placeholder domain (Caddyfile + the
backend `CORS_ORIGINS`) and the ACME email:

```bash
cd /opt/anfinances
sed -i 's/anfinances.example.com/<your-domain>/g' \
    caddy/Caddyfile docker-compose.deploy.yml
sed -i 's/you@example.com/<your-email>/g' caddy/Caddyfile
git commit -am "chore(deploy): set production domain"
git push
```

## 3. Configure CI (GitHub Secrets / Variables)

Settings → Secrets and variables → Actions.

**Secrets:**

| Secret | What |
| --- | --- |
| `SSH_HOST` / `SSH_USER` / `SSH_KEY` / `SSH_PORT` | SSH access to the server. |
| `DEPLOY_PATH` | Repo path on the server (e.g. `/opt/anfinances`). |
| `GHCR_PAT` | GitHub PAT with `read:packages` (to pull private images). |
| `SECRET_KEY` | JWT secret, ≥32 bytes (`openssl rand -hex 32`). |
| `POSTGRES_PASSWORD` | Strong database password (not `anfinances`). |
| `SINGLE_USER_EMAIL` | Login email (single-user mode). |
| `SINGLE_USER_PASSWORD` | Login password (single-user mode). |

The deploy workflow renders `backend/.env` from these secrets. The
non-secret production toggles (`ENVIRONMENT=production`, `DEBUG=false`,
`COOKIE_SECURE=true`, `CORS_ORIGINS`) live in `docker-compose.deploy.yml`
under version control, so the secrets `.env` only needs to carry the
four secrets above (plus whatever the workflow already writes).

`HTTP_PORT` is no longer used (Caddy owns 80/443) and can be removed
from the Variables.

## 4. Deploy

Push to `main` (or run the Deploy workflow manually). It builds the
images, pushes them to GHCR, then over SSH: pulls the images, runs
`docker compose -f docker-compose.deploy.yml up -d`, and applies
`alembic upgrade head`.

On first boot the backend:

- fails fast if the production config is unsafe (debug on, insecure
  cookies, default/placeholder secret, or missing single-user
  credentials),
- creates the single-user account and default categories,
- fetches currency rates.

Caddy requests the certificate on its first start; allow a minute.

## 5. Verify

```bash
curl https://<your-domain>/api/v1/health/ready   # {"status":"ok",...}
```

Then open `https://<your-domain>` and log in with `SINGLE_USER_*`.

If currency rates didn't load (external provider was down at boot):

```bash
docker compose -f docker-compose.deploy.yml exec backend \
    python -m scripts.seed
```

## 6. Backups

- **Application data**: in-app backup (Settings → Data → full JSON),
  or `GET /api/v1/export/all.json`. Restore via Settings → Data →
  Restore (`POST /api/v1/import/all`).
- **Database** (`pg_dump`, schedule via cron):

```bash
docker compose -f docker-compose.deploy.yml exec -T postgres \
    pg_dump -U anfinances anfinances > backup-$(date +%F).sql
```

## 7. Updates

Just push to `main` — CI rebuilds, redeploys, and migrates. No manual
steps on the server. Certificates renew automatically (Caddy).
