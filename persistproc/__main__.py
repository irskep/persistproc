"""
Entry point for the persistproc package.

This module serves as the main entry point when running `python -m persistproc`.
It handles argument parsing and dispatches to either server or client modes.
"""

import os
import sys

# Check for Unix-like system
if os.name != "posix":
    print(
        "Error: persistproc only supports Unix-like systems (Linux, macOS, BSD)",
        file=sys.stderr,
    )
    sys.exit(1)

from .cli import parse_args, run_client
from .server import run_server


def main():
    """Main entry point for persistproc."""
    parser, args = parse_args()

    if args.command:
        # Client mode - run command and tail logs
        run_client(args)
    elif args.serve:
        # Server mode - run MCP server
        run_server(args.host, args.port, args.verbose)
    else:
        # No command provided - show help
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
