FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Зависимости отдельным слоем: код меняется чаще, чем uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# Бот работает от непривилегированного пользователя: наружу он не
# слушает, но и лишних прав ему не нужно.
RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /data \
    && chown -R bot:bot /app /data
USER bot

CMD ["uv", "run", "--no-dev", "python", "-m", "anfinances_bot.main"]
