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

from .cli import (
    parse_args,
    run_and_tail_async,
    tool_command_wrapper,
    log_paths_command,
)
from .server import run_server


def main():
    """Main entry point for the persistproc command."""
    # --- Implicit 'run' subcommand logic ---
    args = sys.argv[1:]
    known_commands = {
        "serve",
        "run",
        "list",
        "status",
        "stop",
        "restart",
        "output",
        "log-paths",
    }
    # Check if the first argument is a known command or an option
    if args and args[0] not in known_commands and not args[0].startswith("-"):
        sys.argv.insert(1, "run")

    parser, args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )
    # Silence the noisy fastmcp logger
    logging.getLogger("fastmcp").setLevel(logging.WARNING)

    if args.subcommand == "serve":
        run_server(args.host, args.port)
    elif args.subcommand == "run":
        if not args.command:
            parser.error("the following arguments are required: command")
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
    elif args.subcommand == "list":
        asyncio.run(tool_command_wrapper(args, "list_processes"))
    elif args.subcommand == "status":
        asyncio.run(tool_command_wrapper(args, "get_process_status", {"pid": args.pid}))
    elif args.subcommand == "stop":
        asyncio.run(
            tool_command_wrapper(
                args, "stop_process", {"pid": args.pid, "force": args.force}
            )
        )
    elif args.subcommand == "restart":
        asyncio.run(tool_command_wrapper(args, "restart_process", {"pid": args.pid}))
    elif args.subcommand == "output":
        params = {"pid": args.pid, "stream": args.stream}
        if args.lines:
            params["lines"] = args.lines
        asyncio.run(tool_command_wrapper(args, "get_process_output", params))
    elif args.subcommand == "log-paths":
        asyncio.run(log_paths_command(args))
    else:
        # No command provided - show help
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
