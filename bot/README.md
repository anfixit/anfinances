# anfinances-bot

Телеграм-бот к [anfinances](../README.md): приём трат голосом и текстом,
ответы на вопросы по данным.

Бот — обычный клиент публичного API anfinances. Прямого доступа к базе
у него нет и не будет.

Дизайн: [docs/superpowers/specs/2026-08-10-telegram-bot-design.md](../docs/superpowers/specs/2026-08-10-telegram-bot-design.md)

## MCP-сервер

Тот же образ запускает и удалённый MCP-сервер для ChatGPT, Claude и
Claude Code: `python -m anfinances_bot.mcp_server`, Streamable HTTP на
`https://anfinances.ru/mcp` (внутри сети — `mcp:8100`).

- Секретов бота серверу не нужно. Каждый запрос приходит с токеном
  подключения (`anf_pat_…` или OAuth `anf_oat_…`); сервер проверяет
  его через `GET /api/v1/ai/whoami` (ответ помнится 30 секунд) и в
  сайт ходит только с ним же. Без токена — 401 с
  `WWW-Authenticate: Bearer resource_metadata=…`, метаданные ресурса —
  на `/.well-known/oauth-protected-resource/mcp`.
- Инструменты — из `agent/tools.py`, список в `mcp_server/catalog.py`.
  Удалений и архивации нет. Пишущие инструменты видны и работают
  только с правом `finance.write`.
- Выписка: `preview_statement` возвращает `preview_id`, а
  `import_statement` без него не пишет. Ходов беседы, как у бота, в
  MCP нет — согласие человека даёт клиент, подтверждая пишущий вызов.
- `idempotency_key` у создающих инструментов: повтор с тем же ключом
  в течение суток возвращает первый ответ и ничего не пишет.

Переменные: `ANFINANCES_BASE_URL`, `MCP_PUBLIC_URL`
(`https://anfinances.ru/mcp`), `MCP_ISSUER` (`https://anfinances.ru`),
`MCP_PORT` (8100), `MCP_TIMEZONE` — если профиль по токену не прочитать,
`BOT_DEFAULT_ACCOUNTS` — необязательно.

## Разработка

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```
