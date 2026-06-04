# syntax=docker/dockerfile:1

# ── builder: зависимости в изолированный venv через uv ─────────────────
FROM python:3.13-slim AS builder

# uv ставим из pip — без зависимости от внешнего ghcr-образа.
RUN pip install --no-cache-dir uv

# venv ВНЕ /app: dev-bind-mount (./backend:/app) не должен его перекрыть.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Ставим только зависимости (не сам проект): слой кешируется по lock-файлу
# и не пересобирается при изменении кода приложения.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# ── runtime: тонкий образ только с venv и кодом ────────────────────────
FROM python:3.13-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Непривилегированный пользователь.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . .

USER app
EXPOSE 8000

# Прод-команда. В dev docker-compose.yml переопределяется на --reload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
