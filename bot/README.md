# anfinances-bot

Телеграм-бот к [anfinances](../README.md): приём трат голосом и текстом,
ответы на вопросы по данным.

Бот — обычный клиент публичного API anfinances. Прямого доступа к базе
у него нет и не будет.

Дизайн: [docs/superpowers/specs/2026-08-10-telegram-bot-design.md](../docs/superpowers/specs/2026-08-10-telegram-bot-design.md)

## Разработка

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```
