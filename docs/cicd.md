# CI/CD

Two GitHub Actions workflows:

- **CI** (`.github/workflows/ci.yml`) — runs on every push and pull request: backend `ruff` + `mypy` + `pytest` (against a throwaway PostgreSQL service) and frontend `tsc` + `eslint` + `build`. This is the quality gate.
- **Deploy** (`.github/workflows/deploy.yml`) — runs on push to `main` (or manually): builds the backend and frontend Docker images, pushes them to GitHub Container Registry (GHCR), then connects to the server over SSH and rolls them out.

## How deploy works

1. `build` job builds two images and pushes them to `ghcr.io/<owner>/<repo>-backend` and `…-frontend`, tagged with both `latest` and the commit SHA.
2. `deploy` job SSHes into the server and:
   - `git pull` (to get the latest `docker-compose.deploy.yml` — it contains **no secrets**),
   - logs in to GHCR,
   - renders `backend/.env` from GitHub Secrets (the secrets never live in git),
   - `docker compose -f docker-compose.deploy.yml pull && up -d`,
   - runs `alembic upgrade head`.

Nothing is built on the server — it only pulls prebuilt images, so it won't compete with other containers (e.g. the kanban app).

## One-time server preparation

```bash
# On the server, as the deploy user:
sudo apt-get update && sudo apt-get install -y git docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # re-login after this

# Clone the repo to the path you'll use as DEPLOY_PATH:
git clone https://github.com/<you>/anfinances.git /opt/anfinances
```

The server needs only `git`, Docker, and the compose plugin — no Node.js, pnpm, uv, or Python.

## Required GitHub Secrets

Settings → Secrets and variables → Actions → **Secrets**:

| Secret | What |
| --- | --- |
| `SSH_HOST` | Server IP (also used as the app origin while there's no domain). |
| `SSH_USER` | SSH user (e.g. `admin`). |
| `SSH_KEY` | Private SSH key (the matching public key is in the server's `authorized_keys`). |
| `SSH_PORT` | SSH port (e.g. `22`). |
| `DEPLOY_PATH` | Repo path on the server (e.g. `/opt/anfinances`). |
| `GHCR_PAT` | A GitHub PAT with `read:packages` (lets the server pull images; needed if the package is private). |
| `SECRET_KEY` | App JWT secret, ≥32 bytes (`openssl rand -hex 32`). |
| `POSTGRES_PASSWORD` | Database password. |
| `SINGLE_USER_EMAIL` | Login email for single-user mode. |
| `SINGLE_USER_PASSWORD` | Login password for single-user mode. |

## Required GitHub Variables

Settings → Secrets and variables → Actions → **Variables**:

| Variable | What |
| --- | --- |
| `HTTP_PORT` | Host port the app listens on. Default `8080` (avoids clashing with anything on `80`). |

## Access the app

While there's no domain, the app is at `http://<SSH_HOST>:<HTTP_PORT>` (e.g. `http://213.171.28.210:8080`). `COOKIE_SECURE` is `false` because the connection is plain HTTP.

## When you get a domain

- Point the domain at the server, switch to the TLS-enabled Nginx + Certbot setup (`docker-compose.prod.yml`, `nginx/nginx.conf`, `scripts/init-letsencrypt.sh`).
- Flip `COOKIE_SECURE=true` and set `CORS_ORIGINS` to `https://your-domain.tld` in the rendered `.env` (update the deploy workflow's heredoc).

## Notes

- The deploy uses [`appleboy/ssh-action`](https://github.com/appleboy/ssh-action). Secrets are passed via `envs:` (kept out of the shell history) and interpolated into the `.env` heredoc on the server.
- Pin actions to a commit SHA instead of a tag if you want stricter supply-chain guarantees.
- Because you posted the server IP/user publicly, rotate the SSH key after first setup.
