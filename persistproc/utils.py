"""
Utility functions for persistproc.

This module contains utility functions for timestamps, command processing,
platform-specific paths, and logging setup.
"""

import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def get_app_data_dir(app_name: str) -> Path:
    """Gets the platform-specific application data directory."""
    if sys.platform == "darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / app_name
    elif sys.platform.startswith("linux"):  # Linux
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / app_name
        return Path.home() / ".local" / "share" / app_name
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    # Fallback for other operating systems
    return Path.home() / f".{app_name}"


def get_iso_timestamp() -> str:
    """Returns the current UTC time in ISO 8601 format."""
    # Use timezone-aware datetime objects as recommended to avoid DeprecationWarning
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def escape_command(command: str) -> str:
    """Sanitizes and truncates a command string for use in filenames."""
    MAX_COMMAND_LEN = 50
    escaped = re.sub(r"\s+", "_", command)
    escaped = re.sub(r"[^a-zA-Z0-9_-]", "", escaped)
    return escaped[:MAX_COMMAND_LEN]


def setup_logging(verbose: bool = False):
    """Setup logging with custom format showing only level and message."""
    level = logging.DEBUG if verbose else logging.INFO

    # Get our specific logger
    log = logging.getLogger("persistproc")
    log.setLevel(level)
    log.propagate = False  # Prevent duplicate logs in root logger
    if log.hasHandlers():
        log.handlers.clear()

    # Console handler with simple format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(console_handler)

    # File handler for persistproc.log with detailed, ISO-formatted timestamps
    from .utils import get_app_data_dir

    APP_DATA_DIR = get_app_data_dir("persistproc")
    LOG_DIRECTORY = APP_DATA_DIR / "logs"
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)

    log_file_path = LOG_DIRECTORY / "persistproc.log"
    file_handler = logging.FileHandler(log_file_path)
    iso_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    iso_formatter.converter = time.gmtime
    file_handler.setFormatter(iso_formatter)
    log.addHandler(file_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    # Let fastmcp log to console, but not to our file
    logging.getLogger("fastmcp").propagate = True
    logging.getLogger("fastmcp").setLevel(logging.INFO)
