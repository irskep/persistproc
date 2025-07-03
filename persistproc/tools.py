from __future__ import annotations

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from persistproc.process_manager import ProcessManager

import logging

from .process_types import (
    ListProcessesResult,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    StartProcessResult,
    StopProcessResult,
    RestartProcessResult,
)

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    call: Callable[..., Any]
    register_tool: Callable[[FastMCP], None]
    build_subparser: Callable[[ArgumentParser], None]
    call_with_args: Callable[[Namespace], Any]

    @property
    def name(self) -> str:  # noqa: D401 – simple property
        return self.call.__name__

    @property
    def description(self) -> str:  # noqa: D401 – simple property
        doc = self.call.__doc__ or ""
        return doc.strip()


def build_start_process_tool(
    process_manager: ProcessManager,
) -> Tool:
    def start_process(
        command: str,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> StartProcessResult:
        # this is the help string for the command line (shorter)
        """Start a new long-running process."""
        logger.info("start_process called – cmd=%s, cwd=%s", command, working_directory)
        return process_manager.start_process(
            command=command,
            working_directory=Path(working_directory) if working_directory else None,
            environment=environment,
        )

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            start_process,
            name="start_process",
            # this is the prompt for the LLM (longer)
            description="Start a new long-running process. REQUIRED if the process is expected to never terminate. PROHIBITED if the process is short-lived.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("command", help="The command to run.")
        parser.add_argument(
            "--working-directory", help="The working directory for the process."
        )
        parser.add_argument(
            "--environment",
            nargs="*",
            help="Environment variables to set for the process, in KEY=VALUE format.",
        )

    def call_with_args(args: Namespace) -> StartProcessResult:
        env = None
        if args.environment:
            env = dict(item.split("=", 1) for item in args.environment)

        return start_process(
            command=args.command,
            working_directory=args.working_directory,
            environment=env,
        )

    # Ensure forward-ref in return annotation is fully-qualified so Pydantic can
    # resolve it even when *globalns* is empty.
    start_process.__annotations__["return"] = "StartProcessResult"

    return Tool(
        call=start_process,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_list_processes_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the list_processes tool and its registration function."""

    def list_processes() -> ListProcessesResult:
        """List all managed processes and their status."""
        logger.debug("list_processes called")
        return process_manager.list_processes()

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            list_processes,
            name="list_processes",
            description="List all managed processes and their status.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        pass

    def call_with_args(args: Namespace) -> ListProcessesResult:
        return list_processes()

    list_processes.__annotations__["return"] = "ListProcessesResult"

    return Tool(
        call=list_processes,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_get_process_status_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the get_process_status tool and its registration function."""

    def get_process_status(pid: int) -> ProcessStatusResult:
        """Get the detailed status of a specific process."""
        logger.debug("get_process_status called for pid=%s", pid)
        return process_manager.get_process_status(pid)

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            get_process_status,
            name="get_process_status",
            description="Get the detailed status of a specific process.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("pid", type=int, help="The process ID.")

    def call_with_args(args: Namespace) -> ProcessStatusResult:
        return get_process_status(pid=args.pid)

    get_process_status.__annotations__["return"] = "ProcessStatusResult"

    return Tool(
        call=get_process_status,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_stop_process_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the stop_process tool and its registration function."""

    def stop_process(pid: int, force: bool = False) -> StopProcessResult:
        """Stop a running process by its PID."""
        logger.info("stop_process called for pid=%s force=%s", pid, force)
        return process_manager.stop_process(pid, force)

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            stop_process,
            name="stop_process",
            description="Stop a running process by its PID.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("pid", type=int, help="The process ID.")
        parser.add_argument(
            "--force", action="store_true", help="Force stop the process."
        )

    def call_with_args(args: Namespace) -> StopProcessResult:
        return stop_process(pid=args.pid, force=args.force)

    stop_process.__annotations__["return"] = "StopProcessResult"

    return Tool(
        call=stop_process,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_restart_process_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the restart_process tool and its registration function."""

    def restart_process(pid: int) -> RestartProcessResult:
        """Stops a process and starts it again with the same parameters."""
        logger.info("restart_process called for pid=%s", pid)
        return process_manager.restart_process(pid)

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            restart_process,
            name="restart_process",
            description="Stops a process and starts it again with the same parameters.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("pid", type=int, help="The process ID.")

    def call_with_args(args: Namespace) -> RestartProcessResult:
        return restart_process(pid=args.pid)

    restart_process.__annotations__["return"] = "RestartProcessResult"

    return Tool(
        call=restart_process,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_get_process_output_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the get_process_output tool and its registration function."""

    def get_process_output(
        pid: int,
        stream: str,
        lines: int | None = None,
        before_time: str | None = None,
        since_time: str | None = None,
    ) -> ProcessOutputResult:
        """Retrieve captured output from a process."""
        logger.debug(
            "get_process_output called pid=%s stream=%s lines=%s before=%s since=%s",
            pid,
            stream,
            lines,
            before_time,
            since_time,
        )
        return process_manager.get_process_output(pid, stream, lines)

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            get_process_output,
            name="get_process_output",
            description="Retrieve captured output from a process.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("pid", type=int, help="The process ID.")
        parser.add_argument(
            "stream", choices=["stdout", "stderr"], help="The output stream to read."
        )
        parser.add_argument(
            "--lines", type=int, help="The number of lines to retrieve."
        )
        parser.add_argument(
            "--before-time", help="Retrieve logs before this timestamp."
        )
        parser.add_argument("--since-time", help="Retrieve logs since this timestamp.")

    def call_with_args(args: Namespace) -> ProcessOutputResult:
        return get_process_output(
            pid=args.pid,
            stream=args.stream,
            lines=args.lines,
            before_time=args.before_time,
            since_time=args.since_time,
        )

    get_process_output.__annotations__["return"] = "ProcessOutputResult"

    return Tool(
        call=get_process_output,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


def build_get_process_log_paths_tool(
    process_manager: ProcessManager,
) -> Tool:
    """Builds the get_process_log_paths tool and its registration function."""

    def get_process_log_paths(pid: int) -> ProcessLogPathsResult:
        """Get the paths to the log files for a specific process."""
        logger.debug("get_process_log_paths called for pid=%s", pid)
        return process_manager.get_process_log_paths(pid)

    def register_tool(mcp: FastMCP) -> None:
        """Registers the tool with a FastMCP instance."""
        tool = FunctionTool.from_function(
            get_process_log_paths,
            name="get_process_log_paths",
            description="Get the paths to the log files for a specific process.",
        )
        mcp.add_tool(tool)

    def build_subparser(parser: ArgumentParser) -> None:
        parser.add_argument("pid", type=int, help="The process ID.")

    def call_with_args(args: Namespace) -> ProcessLogPathsResult:
        return get_process_log_paths(pid=args.pid)

    get_process_log_paths.__annotations__["return"] = "ProcessLogPathsResult"

    return Tool(
        call=get_process_log_paths,
        register_tool=register_tool,
        build_subparser=build_subparser,
        call_with_args=call_with_args,
    )


ALL_TOOL_BUILDERS = [
    build_start_process_tool,
    build_list_processes_tool,
    build_get_process_status_tool,
    build_stop_process_tool,
    build_restart_process_tool,
    build_get_process_output_tool,
    build_get_process_log_paths_tool,
]


def get_tools(process_manager: ProcessManager) -> list[Tool]:
    return [tool_builder(process_manager) for tool_builder in ALL_TOOL_BUILDERS]
