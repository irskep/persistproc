from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

CLI_LOGGER_NAME = "persistproc.cli"


_is_quiet = False
_current_log_path: Path | None = None


def get_log_path(data_dir: Path, timestamp: str | None = None) -> Path:
    """Construct the log file path for a given data directory and optional timestamp.

    If timestamp is None, uses the current timestamp.
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return data_dir / f"persistproc.run.{timestamp}.log"


def find_latest_log_path(data_dir: Path) -> Path | None:
    """Find the most recent log file in the data directory."""
    if not data_dir.exists():
        return None

    log_files = list(data_dir.glob("persistproc.run.*.log"))
    if not log_files:
        return None

    # Return the most recently modified log file
    return max(log_files, key=lambda p: p.stat().st_mtime)


def get_current_log_path() -> Path | None:
    """Get the current log path that was set during setup_logging."""
    return _current_log_path


def _set_current_log_path(path: Path) -> None:
    """Internal function to set the current log path."""
    global _current_log_path
    _current_log_path = path


def get_is_quiet() -> bool:
    return _is_quiet


class CustomFormatter(logging.Formatter):
    regular = "\x1b[37;20m"
    grey = "\x1b[90;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(message)s"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: regular + format + reset,
        logging.ERROR: yellow + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup_logging(verbosity: int, data_dir: Path) -> Path:
    """Configure logging for the current *persistproc* invocation.

    A console handler is configured according to *verbosity* and a file handler
    capturing *all* logs at DEBUG level is written to
    ``data_dir/persistproc.run.<timestamp>.log``.

    The function ensures *data_dir* exists and returns the path to the created
    log file.
    """
    global _is_quiet
    _is_quiet = verbosity <= -1

    # Ensure the directory exists so we can write the log file.
    data_dir.mkdir(parents=True, exist_ok=True)

    log_path = get_log_path(data_dir)
    _set_current_log_path(log_path)

    # We configure the root logger, so all libraries using the standard
    # `logging` module will inherit this configuration.
    root_logger = logging.getLogger()

    # Avoid adding handlers multiple times if this function is called repeatedly,
    # which can happen during tests or complex CLI invocations.
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(logging.DEBUG)

    # ----------------------------------------------------------------------------
    # File handler (always DEBUG)
    # ----------------------------------------------------------------------------
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root_logger.addHandler(file_handler)

    # ----------------------------------------------------------------------------
    # Console handler – behaviour depends on *verbosity*
    # ----------------------------------------------------------------------------
    console_handler = logging.StreamHandler()

    if verbosity <= -1:
        _is_quiet = True
        # Default: only show the dedicated CLI logger at INFO level.
        console_handler.setLevel(logging.WARNING)

        class _CliOnlyFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 – simple predicate
                return record.name.startswith(CLI_LOGGER_NAME)

        console_handler.addFilter(_CliOnlyFilter())
    elif verbosity == 0:
        # Default: only show the dedicated CLI logger at INFO level.
        console_handler.setLevel(logging.INFO)

        class _CliOnlyFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 – simple predicate
                return record.name.startswith(CLI_LOGGER_NAME)

        console_handler.addFilter(_CliOnlyFilter())
    elif verbosity == 1:
        # Show INFO+ from *all* loggers.
        console_handler.setLevel(logging.INFO)
    else:
        # Show DEBUG from *all* loggers.
        console_handler.setLevel(logging.DEBUG)

    if os.isatty(sys.stdout.fileno()):
        console_handler.setFormatter(CustomFormatter())
    else:
        console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # By configuring the root logger, child loggers (like `uvicorn` or
    # `fastmcp`) will automatically propagate their records up, so they will be
    # captured by our file and console handlers. We no longer need to manage
    # the `propagate` flag manually.

    return log_path


CLI_LOGGER = logging.getLogger(CLI_LOGGER_NAME)
