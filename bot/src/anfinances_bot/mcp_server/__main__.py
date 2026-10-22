"""Точка входа MCP-сервера: ``python -m anfinances_bot.mcp_server``."""

import logging

import uvicorn

from anfinances_bot.mcp_server.config import get_mcp_settings
from anfinances_bot.mcp_server.server import build_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = get_mcp_settings()
    uvicorn.run(
        build_app(settings),
        host=settings.mcp_host,
        port=settings.mcp_port,
        # Версия сервера в заголовке никому снаружи не нужна.
        server_header=False,
    )


if __name__ == "__main__":
    main()
