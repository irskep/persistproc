from __future__ import annotations

import logging
import subprocess
import sys
from typing import Sequence


def run(command: str, args: Sequence[str], verbose: int = 0) -> None:  # noqa: D401
    """Run *command* with *args* and stream its output to the console.

    This is *not* the long-running, managed execution path used by
    :pyclass:`~persistproc.process_manager.ProcessManager`.  It is a thin
    convenience wrapper that blocks until the command exits, intended for
    parity with the former CLI implementation until full functionality is
    restored.
    """

    logger = logging.getLogger("persistproc.cli")

    try:
        process = subprocess.Popen(
            [command, *args]
        )  # noqa: S603 – user-supplied command
    except FileNotFoundError:
        logger.error("Command not found: %s", command)
        sys.exit(127)
    except Exception as exc:  # pragma: no cover – safeguard
        logger.exception("Failed to start %s: %s", command, exc)
        sys.exit(1)

    logger.info("Process started (PID %s)", process.pid)

    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        logger.info("Interrupted by user – terminating …")
        process.terminate()
        return_code = process.wait()

    if return_code == 0:
        logger.info("Process exited successfully")
    else:
        logger.warning("Process exited with code %s", return_code)
