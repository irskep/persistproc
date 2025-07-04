from __future__ import annotations

import logging
from pathlib import Path

from fastmcp import FastMCP

from .logging_utils import CLI_LOGGER
from .tools import ALL_TOOL_CLASSES
from .process_manager import ProcessManager

logger = logging.getLogger(__name__)

__all__ = ["serve"]


def _build_app(pm: ProcessManager) -> FastMCP:  # noqa: D401 – helper
    """Return a *FastMCP* application with all *persistproc* tools registered."""

    app = FastMCP(
        "PersistProc",
        "A shared process layer for multi-agent development workflows.",
    )

    for tool_cls in ALL_TOOL_CLASSES:
        tool = tool_cls()
        tool.register_tool(pm, app)

    return app


def serve(
    port: int, verbose: int, data_dir: Path, log_path: Path
) -> None:  # noqa: D401
    """Start the *persistproc* MCP server.

    By default this function logs the intended bind address and *returns* so
    that the CLI command remains a *no-op* (this matches the behaviour expected
    by the current test-suite).

    Passing ``foreground=True`` starts the FastMCP HTTP server and blocks the
    current thread until the server is stopped (eg. via *Ctrl+C*).
    """

    logger.debug("Verbose level requested: %d", verbose)

    # The server blocks in the foreground until interrupted.

    pm = ProcessManager()
    pm.bootstrap(data_dir, server_log_path=log_path)
    app = _build_app(pm)

    CLI_LOGGER.info("Starting MCP server on http://127.0.0.1:%d", port)

    try:
        app.run(transport="http", host="127.0.0.1", port=port, path="/mcp/")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested (Ctrl+C)")
    finally:
        logger.info("Server process exiting")
