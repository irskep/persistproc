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

    subparsers = parser.add_subparsers(dest="command")

    def add_common_args(parser):
        parser.add_argument("--port", type=int, default=get_default_port())
        parser.add_argument("--data-dir", type=Path, default=get_default_data_dir())
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
    for tool in get_tools(process_manager):
        p_tool = subparsers.add_parser(tool.name, help=tool.description)
        tool.build_subparser(p_tool)
    tools_by_name = {tool.name: tool for tool in get_tools(process_manager)}

    # ---------------------------------------------------------------------
    # Configure logging *before* doing anything substantial so that any
    # subsequent code can rely on it.
    # ---------------------------------------------------------------------

    # We'll run argument parsing twice: the first pass (here) **ignores**
    # sub-command specific arguments so that we can extract *verbosity* and
    # *data_dir* early.  This ensures that log messages emitted while
    # building sub-parsers are still captured.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--data-dir", type=Path, default=get_default_data_dir())
    pre_parser.add_argument("-v", "--verbose", action="count", default=0)
    pre_args, _ = pre_parser.parse_known_args()

    log_path = setup_logging(pre_args.verbose or 0, pre_args.data_dir)

    cli_logger = logging.getLogger(CLI_LOGGER_NAME)

    recognised_subcommands = {"serve", "run", *tools_by_name.keys()}

    # ------------------------------------------------------------------
    # Fast-path: if the first non-option argument is *not* a recognised
    # sub-command, interpret it as an implicit `run` invocation **before** we
    # call `parser.parse_args` (which would otherwise error-exit).
    # ------------------------------------------------------------------

    raw_argv = sys.argv[1:]
    try:
        first_pos = next(i for i, tok in enumerate(raw_argv) if not tok.startswith("-"))
    except StopIteration:
        # No positional arguments at all → fall back to full argparse parsing
        first_pos = None

    if first_pos is not None and raw_argv[first_pos] not in recognised_subcommands:
        command = raw_argv[first_pos]
        run_args = raw_argv[first_pos + 1 :]

        # Apply the same heuristic used by the explicit `run` sub-command: if
        # the *command* token itself contains spaces **and** no additional
        # arguments were supplied, treat it as a quoted composite command and
        # split it with *shlex.split*.
        if " " in command and not run_args:
            parts = shlex.split(command)
            command = parts[0]
            run_args = parts[1:]

        cli_logger.info(
            "(implicit run) Running command: %s %s", command, " ".join(run_args)
        )

        # Initialise ProcessManager now that *args.data_dir* is known.
        process_manager.bootstrap(pre_args.data_dir, server_log_path=log_path)

        run(command, run_args, pre_args.verbose, raw=False)
        return  # done

    # ------------------------------------------------------------------
    # Normal code-path – parse the full CLI grammar.
    # ------------------------------------------------------------------

    args = parser.parse_args()

    # Inform user where the detailed log file is written.
    cli_logger.info("Verbose log written to %s", log_path)

    # Initialise ProcessManager now that *args.data_dir* is known.
    process_manager.bootstrap(args.data_dir, server_log_path=log_path)

    if args.command == "serve":
        cli_logger.info("Starting server on port %d", args.port)
        serve(
            args.port,
            args.verbose,
            process_manager=process_manager,
        )
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
