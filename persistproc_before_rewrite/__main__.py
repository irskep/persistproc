"""
Entry point for the persistproc package.

This module serves as the main entry point when running `python -m persistproc`.
It handles argument parsing and dispatches to either server or client modes.
"""

import os
import sys
import asyncio
import logging

# Check for Unix-like system
if os.name != "posix":
    print(
        "Error: persistproc only supports Unix-like systems (Linux, macOS, BSD)",
        file=sys.stderr,
    )
    sys.exit(1)

from .cli import parse_args, run_and_tail_async
from .server import run_server


def main():
    """Main entry point for the persistproc command."""
    parser, args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )
    # Silence the noisy fastmcp logger
    logging.getLogger("fastmcp").setLevel(logging.WARNING)

    if args.serve:
        run_server(args.host, args.port)
    elif args.command:
        try:
            asyncio.run(run_and_tail_async(args))
        except KeyboardInterrupt:
            # This is a fallback. The CLI's async code tries to handle Ctrl+C
            # more gracefully. This can be triggered if Ctrl+C is pressed
            # very early during CLI startup.
            print(
                "\n--- Detaching from log tailing. Process remains running. ---",
                file=sys.stderr,
            )
    else:
        # No command provided - show help
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
