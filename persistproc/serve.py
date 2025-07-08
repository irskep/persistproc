from __future__ import annotations

import logging
from pathlib import Path

from fastmcp import FastMCP
from rich import print, print_json

from .console import console
from .logging_utils import CLI_LOGGER, get_is_quiet
from .process_manager import ProcessManager
from .tools import ALL_TOOL_CLASSES

logger = logging.getLogger(__name__)

__all__ = ["serve"]


def _build_app(pm: ProcessManager) -> FastMCP:  # noqa: D401 – helper
    """Return a *FastMCP* application with all *persistproc* tools registered."""

    app = FastMCP(
        "persistproc",
        "Manage long-running processes and read their output. Full documentation is available at https://steveasleep.com/persistproc/.",
    )

    for tool_cls in ALL_TOOL_CLASSES:
        tool = tool_cls()
        tool.register_tool(pm, app)

    return app


def serve(port: int, data_dir: Path, server_log_path: Path | None = None) -> None:  # noqa: D401
    """Start the *persistproc* MCP server.

    By default this function logs the intended bind address and *returns* so
    that the CLI command remains a *no-op* (this matches the behaviour expected
    by the current test-suite).

    Passing ``foreground=True`` starts the FastMCP HTTP server and blocks the
    current thread until the server is stopped (eg. via *Ctrl+C*).
    """

    # The server blocks in the foreground until interrupted.

    pm = ProcessManager(server_log_path, data_dir=data_dir)
    app = _build_app(pm)

    url = f"http://127.0.0.1:{port}/mcp/"
    CLI_LOGGER.info("Starting MCP server on %s", url)

    if not get_is_quiet():
        # centered, with ------ lines above and below
        console.rule("[bold yellow]Cursor[/bold yellow]")
        print("In ~/.cursor/mcp.json:")
        print_json(data={"mcpServers": {"persistproc": {"url": url}}})
        console.rule("[bold yellow]Claude Code[/bold yellow]")
        print()
        print(f"claude mcp add --transport http persistproc {url}")
        print()
        console.rule("[bold yellow]Gemini CLI[/bold yellow]")
        print("In ~/.gemini/settings.json:")
        print_json(
            data={
                "mcpServers": {
                    "persistproc": {
                        "command": "npx",
                        "args": ["mcp-remote", url, "--transport", "http-only"],
                    }
                }
            }
        )
        console.rule("[bold yellow]Other[/bold yellow]")
        print()
        print(f"persistproc uses the HTTP transport protocol on {url}.")
        print("Read your agent's documentation to learn how to hook it up.")
        print()
        print(
            "[link=https://www.anthropic.com/products/claude-desktop]Claude Desktop[/link]"
        )
        print()
        print("[link=https://docs.codeium.com/windsurf/mcp]Windsurf[/link]")
        print()
        print(
            "[link=https://github.com/openai/codex?tab=readme-ov-file#model-context-protocol-mcp]Codex CLI[/link]"
        )
        print()
        console.rule()

    try:
        app.run(transport="http", host="127.0.0.1", port=port, path="/mcp/")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested (Ctrl+C)")
    finally:
        logger.info("Server process exiting")
