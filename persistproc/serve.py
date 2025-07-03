from __future__ import annotations

import logging


def serve(port: int, verbose: int = 0) -> None:  # noqa: D401
    """Placeholder implementation for the *serve* sub-command.

    A full HTTP implementation is outside the scope of this rewrite step; for
    now we only demonstrate the logging facilities described in
    ``internal_docs/logging_strategy.md``.
    """

    logger = logging.getLogger("persistproc.cli")

    logger.info("(stub) Starting MCP server on http://127.0.0.1:%d", port)
    logger.debug("Verbose level requested: %d", verbose)

    # NOTE: This is a *stub* – in future this will start an ASGI/HTTP server.
    logger.warning(
        "Server functionality has not been implemented yet – this is a placeholder"
    )
