from __future__ import annotations

import logging

from fastmcp import FastMCP

from .tools import get_tools
from .process_manager import ProcessManager

logger = logging.getLogger("persistproc.cli")

__all__ = ["serve"]


def _build_app(pm: ProcessManager) -> FastMCP:  # noqa: D401 – helper
    """Return a *FastMCP* application with all *persistproc* tools registered."""

    app = FastMCP(
        "PersistProc",
        "A shared process layer for multi-agent development workflows.",
    )

    for tool in get_tools(pm):
        tool.register_tool(app)

    return app


def serve(
    port: int,
    verbose: int = 0,
    *,
    process_manager: ProcessManager,
) -> None:  # noqa: D401
    """Start the *persistproc* MCP server.

    By default this function logs the intended bind address and *returns* so
    that the CLI command remains a *no-op* (this matches the behaviour expected
    by the current test-suite).

    Passing ``foreground=True`` starts the FastMCP HTTP server and blocks the
    current thread until the server is stopped (eg. via *Ctrl+C*).
    """

    logger.info("Starting MCP server on http://127.0.0.1:%d", port)
    logger.debug("Verbose level requested: %d", verbose)

    # The server blocks in the foreground until interrupted.

    pm = process_manager
    app = _build_app(pm)

    # FastMCP provides an ASGI app with convenience *run* method similar to
    # FastAPI's.  The call blocks until the server exits.
    logger.info(
        "MCP server now accepting connections on http://127.0.0.1:%d/mcp/", port
    )
    try:
        app.run(transport="http", host="127.0.0.1", port=port, path="/mcp/")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested (Ctrl+C)")
    finally:
        logger.info("Server process exiting")
