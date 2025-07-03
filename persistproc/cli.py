import argparse
import os
import shlex
import sys
from pathlib import Path
import logging
from dataclasses import dataclass
from argparse import Namespace
from typing import Union

from .run import run
from .serve import serve
from .tools import ALL_TOOL_CLASSES
from .logging_utils import CLI_LOGGER_NAME, setup_logging

ENV_PORT = "PERSISTPROC_PORT"
ENV_DATA_DIR = "PERSISTPROC_DATA_DIR"


@dataclass
class ServeAction:
    """Represents the 'serve' command."""

    port: int
    data_dir: Path
    verbose: int
    log_path: Path


@dataclass
class RunAction:
    """Represents the 'run' command."""

    command: str
    run_args: list[str]
    fresh: bool
    on_exit: str
    raw: bool
    port: int
    data_dir: Path
    verbose: int


@dataclass
class ToolAction:
    """Represents a tool command."""

    args: Namespace


CLIAction = Union[ServeAction, RunAction, ToolAction]


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


def parse_cli(argv: list[str]) -> tuple[CLIAction, Path]:
    """Parse command line arguments and return a CLIAction and log path."""
    parser = argparse.ArgumentParser(
        description="Process manager for multi-agent development workflows"
    )

    # ------------------------------------------------------------------
    # Logging setup (first lightweight parse just for logging config)
    # ------------------------------------------------------------------
    logging_parser = argparse.ArgumentParser(add_help=False)
    logging_parser.add_argument("--data-dir", type=Path, default=get_default_data_dir())
    logging_parser.add_argument("-v", "--verbose", action="count", default=0)
    logging_args, remaining_argv = logging_parser.parse_known_args(argv)

    log_path = setup_logging(logging_args.verbose or 0, logging_args.data_dir)

    # ------------------------------------------------------------------
    # Helper to avoid repeating common options on every sub-command
    # ------------------------------------------------------------------

    def add_common_args(p: argparse.ArgumentParser) -> None:  # noqa: D401
        """Add --port, --data-dir and -v/--verbose options to *p*."""

        p.add_argument(
            "--port",
            type=int,
            default=get_default_port(),
            help=f"Server port (default: {get_default_port()}; env: ${ENV_PORT})",
        )
        p.add_argument(
            "--data-dir",
            type=Path,
            default=get_default_data_dir(),
            help=f"Data directory (default: {get_default_data_dir()}; env: ${ENV_DATA_DIR})",
        )
        p.add_argument(
            "-v",
            "--verbose",
            action="count",
            default=0,
            help="Increase verbosity; you can use -vv for more",
        )

    # Main parser / sub-commands ------------------------------------------------

    subparsers = parser.add_subparsers(dest="command")

    # Serve command
    p_serve = subparsers.add_parser("serve", help="Start the MCP server")
    add_common_args(p_serve)

    # Run command
    p_run = subparsers.add_parser(
        "run",
        help="Make sure a process is running and tail its output (stdout and stderr) to stdout",
    )
    p_run.add_argument(
        "program",
        help="The program to run (e.g. 'python' or 'ls'). If the string contains spaces, it will be shell-split unless additional arguments are provided separately.",
    )
    p_run.add_argument(
        "args", nargs=argparse.REMAINDER, help="Arguments to the program"
    )
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

    # Tool commands
    tools = [tool_cls() for tool_cls in ALL_TOOL_CLASSES]
    tools_by_name = {tool.name: tool for tool in tools}
    for tool in tools:
        p_tool = subparsers.add_parser(tool.name, help=tool.description)
        add_common_args(p_tool)
        tool.build_subparser(p_tool)

    # Argument parsing
    if not argv:
        # No arguments at all -> default to `serve`
        args = parser.parse_args(["serve"])
    else:
        # Detect the first *real* command in the argv list. We iterate over the
        # raw argument vector, skipping option flags (that start with "-") **and**
        # their values.  If an arg immediately follows an option flag we treat it as
        # that option's value – not as the sub-command.

        first_cmd: str | None = None
        i = 0
        while i < len(argv):
            token = argv[i]
            if token.startswith("-"):
                # Skip the option flag itself as well as its *possible* value.
                # This is a heuristic – it will incorrectly skip a value for a
                # boolean flag (which has no value), but in that case the value
                # also starts with "-" or does not exist, so the next iteration
                # handles it correctly.
                if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    i += 2
                else:
                    i += 1
                continue

            # Non-flag token found – treat it as the prospective sub-command.
            first_cmd = token
            break

        if first_cmd is None:
            # Only global/serve flags – default to `serve`
            args = parser.parse_args(["serve"] + argv)
        elif first_cmd in subparsers.choices:
            # Explicit command provided
            args = parser.parse_args(argv)
        else:
            # Implicit `run` command
            args = parser.parse_args(["run"] + argv)

    # Action creation
    action: CLIAction
    if args.command == "serve":
        action = ServeAction(
            port=args.port,
            data_dir=args.data_dir,
            verbose=args.verbose,
            log_path=log_path,
        )
    elif args.command == "run":
        if " " in args.program and not args.args:
            parts = shlex.split(args.program)
            command = parts[0]
            run_args = parts[1:]
        else:
            command = args.program
            run_args = args.args
        action = RunAction(
            command=command,
            run_args=run_args,
            fresh=args.fresh,
            on_exit=args.on_exit,
            raw=args.raw,
            port=args.port,
            data_dir=args.data_dir,
            verbose=args.verbose,
        )
    elif args.command in tools_by_name:
        action = ToolAction(args=args)
    else:
        parser.print_help()
        sys.exit(1)

    return action, log_path


def handle_cli_action(action: CLIAction, log_path: Path) -> None:
    """Execute the action determined by the CLI."""
    cli_logger = logging.getLogger(CLI_LOGGER_NAME)
    cli_logger.info("Verbose log written to %s", log_path)

    if isinstance(action, ServeAction):
        cli_logger.info("Starting server on port %d", action.port)
        serve(action.port, action.verbose, action.data_dir, action.log_path)
    elif isinstance(action, RunAction):
        cli_logger.info(
            "Running command: %s %s", action.command, " ".join(action.run_args)
        )
        run(
            action.command,
            action.run_args,
            action.verbose,
            fresh=action.fresh,
            on_exit=action.on_exit,
            raw=action.raw,
        )
    elif isinstance(action, ToolAction):
        tools = [tool_cls() for tool_cls in ALL_TOOL_CLASSES]
        tools_by_name = {tool.name: tool for tool in tools}
        tool = tools_by_name[action.args.command]
        tool.call_with_args(action.args)


def cli() -> None:
    """Main CLI entry point."""
    try:
        action, log_path = parse_cli(sys.argv[1:])
        handle_cli_action(action, log_path)
    except SystemExit as e:
        if e.code != 0:
            # argparse prints help and exits, so we only need to re-raise for actual errors
            raise


__all__ = [
    "cli",
    "parse_cli",
    "handle_cli_action",
    "ServeAction",
    "RunAction",
    "ToolAction",
    "CLIAction",
]
