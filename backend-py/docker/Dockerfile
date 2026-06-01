# syntax=docker/dockerfile:1.7

# ─── Stage 1: builder ────────────────────────────────────────────────
# Используем официальный образ uv поверх Python 3.13-slim.
# uv ставит зависимости быстро и воспроизводимо через uv.lock.
FROM python:3.13-slim AS builder

# uv — самый быстрый Python package manager. Тянем его через copy --from.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Сначала только манифест зависимостей — для кеширования слоя.
# Если pyproject.toml/uv.lock не менялись, слой переиспользуется при пересборке.
COPY pyproject.toml uv.lock* ./

# --frozen: упасть если lock-файл не совпадает с pyproject. На первой сборке
# (когда uv.lock ещё нет) используем без --frozen, чтобы uv его сгенерировал.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-dev; \
    else \
        uv sync --no-install-project --no-dev; \
    fi


# ─── Stage 2: runtime ────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Системные либы для asyncpg и bcrypt — минимальный набор.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный юзер.
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# Виртуалка из builder-стадии.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

# Код приложения.
COPY --chown=app:app . /app

USER app

EXPOSE 8000

# Healthcheck стучится в /health/live (не trogает БД, чтобы не флапать
# при временных проблемах с Postgres).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

# В dev compose переопределит CMD на --reload. В prod — этот.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
