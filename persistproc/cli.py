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


def get_default_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "persistproc"
    elif sys.platform.startswith("linux"):
        return (
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            / "persistproc"
        )
    return Path.home() / ".persistproc"


def cli():
    parser = argparse.ArgumentParser(
        description="Process manager for multi-agent development workflows"
    )

    subparsers = parser.add_subparsers(dest="command")

    def add_common_args(parser):
        parser.add_argument("--port", type=int, default=8947)
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
    p_run.add_argument("command", help="The command to run")
    p_run.add_argument("args", nargs="*", help="Arguments to the command")
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

    args = parser.parse_args()

    # Inform user where the detailed log file is written.
    cli_logger.info("Verbose log written to %s", log_path)

    # Initialise ProcessManager now that *args.data_dir* is known.
    process_manager.bootstrap(args.data_dir)

    if args.command == "serve":
        cli_logger.info("Starting server on port %d", args.port)
        serve(args.port, args.verbose)
    elif args.command == "run":
        if " " in args.command and not args.args:
            parts = shlex.split(args.command)
            command = parts[0]
            run_args = parts[1:]
        else:
            command = args.command
            run_args = args.args
        cli_logger.info("Running command: %s %s", command, " ".join(run_args))
        run(command, run_args, args.verbose)
    elif args.command in tools_by_name:
        tool = tools_by_name[args.command]
        tool.call_with_args(args)
    else:
        parser.print_help()
