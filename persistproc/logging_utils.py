from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

CLI_LOGGER_NAME = "persistproc.cli"


def setup_logging(verbosity: int, data_dir: Path) -> Path:
    """Configure logging for the current *persistproc* invocation.

    A console handler is configured according to *verbosity* and a file handler
    capturing *all* logs at DEBUG level is written to
    ``data_dir/persistproc.run.<timestamp>.log``.

    The function ensures *data_dir* exists and returns the path to the created
    log file.
    """
    # Ensure the directory exists so we can write the log file.
    data_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = data_dir / f"persistproc.run.{timestamp}.log"

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

    if verbosity <= 0:
        # Default: only show the dedicated CLI logger at INFO level.
        console_handler.setLevel(logging.INFO)

        class _CliOnlyFilter(logging.Filter):
            def filter(
                self, record: logging.LogRecord
            ) -> bool:  # noqa: D401 – simple predicate
                return record.name.startswith(CLI_LOGGER_NAME)

        console_handler.addFilter(_CliOnlyFilter())
    elif verbosity == 1:
        # Show INFO+ from *all* loggers.
        console_handler.setLevel(logging.INFO)
    else:
        # Show DEBUG from *all* loggers.
        console_handler.setLevel(logging.DEBUG)

    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # By configuring the root logger, child loggers (like `uvicorn` or
    # `fastmcp`) will automatically propagate their records up, so they will be
    # captured by our file and console handlers. We no longer need to manage
    # the `propagate` flag manually.

    return log_path
