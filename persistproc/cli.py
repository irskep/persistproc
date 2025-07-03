import argparse
import os
import shlex
import sys
from pathlib import Path
import logging

from .process_manager import ProcessManager
from .run import run
from .serve import serve
from .tools import get_tools
from .logging_utils import CLI_LOGGER_NAME, setup_logging

ENV_PORT = "PERSISTPROC_PORT"
ENV_DATA_DIR = "PERSISTPROC_DATA_DIR"


def get_default_data_dir() -> Path:
    """Return default data directory, honouring *PERSISTPROC_DATA_DIR*."""

    if ENV_DATA_DIR in os.environ and os.environ[ENV_DATA_DIR]:
        return Path(os.environ[ENV_DATA_DIR]).expanduser().resolve()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "persistproc"
    elif sys.platform.startswith("linux"):
        return (
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            / "persistproc"
        )
    return Path.home() / ".persistproc"


def get_default_port() -> int:
    """Return default port, honouring *PERSISTPROC_PORT*."""

    if ENV_PORT in os.environ:
        try:
            return int(os.environ[ENV_PORT])
        except ValueError:
            pass  # fall through to hard-coded default

    return 8947


def cli():
    parser = argparse.ArgumentParser(
        description="Process manager for multi-agent development workflows"
    )

    # ---------------------------------------------------------------------
    # Logging setup: we need to parse arguments *twice*. The first pass is
    # with a minimal parser to extract only what's needed for logging, so
    # that we can begin capturing messages ASAP.
    # ---------------------------------------------------------------------
    logging_parser = argparse.ArgumentParser(add_help=False)
    logging_parser.add_argument("--data-dir", type=Path, default=get_default_data_dir())
    logging_parser.add_argument("-v", "--verbose", action="count", default=0)
    logging_args, remaining_argv = logging_parser.parse_known_args()

    log_path = setup_logging(logging_args.verbose or 0, logging_args.data_dir)
    cli_logger = logging.getLogger(CLI_LOGGER_NAME)

    # ---------------------------------------------------------------------
    # Main parser configuration
    # ---------------------------------------------------------------------

    subparsers = parser.add_subparsers(dest="command")

    def add_common_args(parser):
        parser.add_argument(
            "--port",
            type=int,
            default=get_default_port(),
            help=f"Server port (default: {get_default_port()}; env: ${ENV_PORT})",
        )
        parser.add_argument(
            "--data-dir",
            type=Path,
            default=get_default_data_dir(),
            help=f"Data directory (default: {get_default_data_dir()}; env: ${ENV_DATA_DIR})",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase verbosity; you can use -vv for more",
        )

    p_serve = subparsers.add_parser("serve", help="Start the MCP server")
    add_common_args(p_serve)

    p_run = subparsers.add_parser(
        "run",
        help="Make sure a process is running and tail its output (stdout and stderr) to stdout",
    )
    p_run.add_argument(
        "program",
        help="The program to run (e.g. 'python' or 'ls'). If the string contains spaces, it will be shell-split unless additional arguments are provided separately.",
    )
    p_run.add_argument("args", nargs="*", help="Arguments to the program")
    p_run.add_argument(
        "--fresh",
        action="store_true",
        help="Stop an existing running instance of the same command before starting a new one.",
    )
    p_run.add_argument(
        "--on-exit",
        choices=["ask", "stop", "detach"],
        default="ask",
        help="Behaviour when you press Ctrl+C: ask (default), stop the process, or detach and leave it running.",
    )
    p_run.add_argument(
        "--raw",
        action="store_true",
        help="Show raw timestamped log lines (default strips ISO timestamps).",
    )
    add_common_args(p_run)

    process_manager = ProcessManager()
    tools = get_tools(process_manager)
    tools_by_name = {tool.name: tool for tool in tools}
    for tool in tools:
        p_tool = subparsers.add_parser(tool.name, help=tool.description)
        add_common_args(p_tool)
        tool.build_subparser(p_tool)

    # ---------------------------------------------------------------------
    # Parse arguments, handling implicit `run` and default `serve`
    # ---------------------------------------------------------------------
    argv = sys.argv[1:]
    if not argv:
        # `persistproc` → `persistproc serve`
        args = parser.parse_args(["serve"])
    else:
        # If the first non-flag argument isn't a known command, inject `run`.
        # e.g. `persistproc my-script.py` → `persistproc run my-script.py`
        first_positional = next((arg for arg in argv if not arg.startswith("-")), None)

        # `persistproc --port=...` -> `persistproc serve --port=...`
        if first_positional is None:
            # Only flags are present, assume `serve`
            argv.insert(0, "serve")
        elif first_positional not in subparsers.choices:
            # Find the position of the first positional argument to insert `run` before it
            insert_at = argv.index(first_positional)
            argv.insert(insert_at, "run")
        args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    # Inform user where the detailed log file is written.
    cli_logger.info("Verbose log written to %s", log_path)

    # Initialise ProcessManager *only* for commands that use it directly
    # (`serve`). Tool calls connect to a server instead.
    if args.command == "serve":
        process_manager.bootstrap(args.data_dir, server_log_path=log_path)
        cli_logger.info("Starting server on port %d", args.port)
        serve(args.port, args.verbose, process_manager=process_manager)
    elif args.command == "run":
        if " " in args.program and not args.args:
            parts = shlex.split(args.program)
            command = parts[0]
            run_args = parts[1:]
        else:
            command = args.program
            run_args = args.args
        cli_logger.info("Running command: %s %s", command, " ".join(run_args))
        run(
            command,
            run_args,
            args.verbose,
            fresh=args.fresh,
            on_exit=args.on_exit,
            raw=args.raw,
        )
    elif args.command in tools_by_name:
        tool = tools_by_name[args.command]
        tool.call_with_args(args)
    else:
        parser.print_help()

    # End of CLI dispatch
