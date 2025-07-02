"""
MCP server setup and signal handling.

This module contains the FastMCP app creation and server-side
signal handling for graceful shutdown.
"""

import logging
import os
import signal
import sys
from typing import Optional

# Check for Unix-like system
if os.name != "posix":
    print(
        "Error: persistproc only supports Unix-like systems (Linux, macOS, BSD)",
        file=sys.stderr,
    )
    sys.exit(1)

from fastmcp import FastMCP

from .core import ProcessManager
from .tools import create_tools
from .utils import get_app_data_dir

# This global variable will hold the single ProcessManager instance.
process_manager: Optional[ProcessManager] = None

logger = logging.getLogger("persistproc")


def create_app(pm: Optional[ProcessManager] = None) -> FastMCP:
    """Create and configure the FastMCP application."""
    global process_manager
    if pm:
        process_manager = pm
    elif process_manager is None:
        APP_DATA_DIR = get_app_data_dir("persistproc")
        LOG_DIRECTORY = APP_DATA_DIR / "logs"
        LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        process_manager = ProcessManager(log_directory=LOG_DIRECTORY)

    app = FastMCP(
        "PersistProc",
        "A shared process layer for multi-agent development workflows.",
    )
    app.process_manager = process_manager
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
