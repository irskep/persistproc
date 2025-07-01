"""
MCP server setup and signal handling.

This module contains the FastMCP app creation and server-side
signal handling for graceful shutdown.
"""

import logging
import signal
import sys

from fastmcp import FastMCP

from .core import ProcessManager
from .tools import create_tools
from .utils import get_app_data_dir

logger = logging.getLogger("persistproc")

# Global process manager instance
process_manager = None


def create_app():
    """Create and configure the FastMCP app with tools."""
    app = FastMCP("persistproc")

    # Register all tools
    create_tools(app, process_manager)

    return app


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        # Stop all running processes
        for pid, p_info in process_manager.processes.items():
            if p_info.status == "running":
                try:
                    process_manager.stop_process(pid)
                    logger.info(f"Stopped process {pid}")
                except Exception as e:
                    logger.error(f"Error stopping process {pid}: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def run_server(host: str = "127.0.0.1", port: int = 8947, verbose: bool = False):
    """Run the MCP server."""
    global process_manager

    from .utils import setup_logging

    setup_logging(verbose)

    logger.info("--- PersistProc Server Starting ---")

    # Initialize app data directory and log directory
    APP_DATA_DIR = get_app_data_dir("persistproc")
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIRECTORY = APP_DATA_DIR / "logs"

    logger.info(f"Log directory: {LOG_DIRECTORY.resolve()}")

    logger.debug(f"Initializing ProcessManager with log_directory={LOG_DIRECTORY}")
    process_manager = ProcessManager(LOG_DIRECTORY)

    logger.debug("Creating FastMCP app")
    app = create_app()

    logger.debug("Setting up signal handlers")
    setup_signal_handlers()

    logger.info(f"Starting PersistProc MCP Server on {host}:{port}")
    app.run(transport="http", host=host, port=port, path="/mcp/")
