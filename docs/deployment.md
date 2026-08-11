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

## 8. TLS certificates

Caddy obtains and renews certificates from Let's Encrypt automatically.
Two conditions must hold, and both fail silently — the site keeps
serving until the certificate expires months later.

**The domain must point straight at the server.** With a proxy in
front (Cloudflare's orange cloud, for instance), Let's Encrypt reaches
the proxy instead of the origin and the TLS-ALPN challenge never
arrives.

**Port 80 must be open and forwarded to Caddy.** If a system nginx
owns port 80, it has to hand `/.well-known/acme-challenge/` to Caddy
rather than serve it from a certbot webroot. See
[nginx-acme.conf](nginx-acme.conf) for the block this deployment uses;
copy it to `/etc/nginx/sites-available/` and symlink it into
`sites-enabled/`.

Check both at once by looking at when the certificate was issued:

```bash
echo | openssl s_client -connect anfinances.ru:443 -servername anfinances.ru 2>/dev/null | openssl x509 -noout -dates
```

A `notBefore` older than 90 days means renewal has been failing.

## 9. Backups

A systemd timer runs `scripts/backup.sh` nightly. It dumps the database,
**restores the dump into a scratch database and compares transaction
counts against the live one**, encrypts the result with AES-256, and
sends it to the owner's Telegram chat. A dump that does not restore is
never sent — instead an alert goes to the same chat.

The passphrase comes from the `BACKUP_PASSPHRASE` secret. Store it in a
password manager: without it the archives cannot be read, and they are
the only offsite copy.

Restore:

```bash
gpg --output anfinances.dump --decrypt anfinances_2026-08-11_0230.dump.gpg
docker exec -i anfinances-postgres pg_restore -U anfinances -d anfinances --clean --no-owner < anfinances.dump
```

Run one on demand, or check when the last one ran:

```bash
sudo systemctl start anfinances-backup.service && systemctl list-timers anfinances-backup.timer
```
