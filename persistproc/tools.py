from __future__ import annotations

import abc
import os
import shlex
from argparse import ArgumentParser, Namespace
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from persistproc.process_manager import ProcessManager

from .mcp_client_utils import execute_mcp_request
from .process_types import (
    KillPersistprocResult,
    ListProcessesResult,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    RestartProcessResult,
    StartProcessResult,
    StopProcessResult,
    StreamEnum,
)

import logging

logger = logging.getLogger(__name__)


def _parse_target_to_pid_or_command_or_label(
    target: str, args: list[str]
) -> tuple[int | None, str | None]:
    """Parse target and args into (pid, command_or_label).

    Returns:
        (pid, command_or_label) where exactly one will be non-None
    """
    if not args:
        # Single target argument - could be PID or command_or_label
        try:
            pid = int(target)
            return pid, None
        except ValueError:
            # Not a PID, treat as command_or_label
            return None, target
    else:
        # Multiple arguments - treat as command with args
        command_or_label = shlex.join([target] + args)
        return None, command_or_label


class ITool(abc.ABC):
    """Abstract base class for a persistproc tool."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the tool."""
        ...

    @property
    @abc.abstractmethod
    def cli_description(self) -> str:
        """The description of the tool for a human user on the command line."""
        ...

    @property
    @abc.abstractmethod
    def mcp_description(self) -> str:
        """The description of the tool for an MCP client with an LLM agent user."""
        ...

    @abc.abstractmethod
    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        """Register the tool with the MCP server."""
        ...

    @abc.abstractmethod
    def build_subparser(self, parser: ArgumentParser) -> None:
        """Configure the CLI subparser for the tool."""
        ...

    @abc.abstractmethod
    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        """Execute the tool's CLI command."""
        ...


class StartProcessTool(ITool):
    name = "start"
    cli_description = "Start a new process"
    mcp_description = "Start a new long-running process. REQUIRED if the process is expected to never terminate. PROHIBITED if the process is short-lived."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        command: str,
        working_directory: str,
        environment: dict[str, str] | None = None,
        label: str | None = None,
    ) -> StartProcessResult:
        """Start a new long-running process."""
        logger.info("start called – cmd=%s, cwd=%s", command, working_directory)
        return process_manager.start(
            command=command,
            working_directory=Path(working_directory),
            environment=environment,
            label=label,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def start(
            command: str,
            working_directory: str,
            environment: dict[str, str] | None = None,
            label: str | None = None,
        ) -> StartProcessResult:
            return self._apply(
                process_manager, command, working_directory, environment, label
            )

        mcp.add_tool(
            FunctionTool.from_function(
                start, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )
        parser.add_argument(
            "--label",
            type=str,
            help="Custom label for the process (default: '<command> in <working_directory>').",
        )
        parser.add_argument("command_", metavar="COMMAND", help="The command to run.")
        parser.add_argument("args", nargs="*", help="Arguments to the command")

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        # Construct the command string from command and args
        if args.args:
            command = shlex.join([args.command_] + args.args)
        else:
            command = args.command_

        payload = {
            "command": command,
            "working_directory": args.working_directory,
            "environment": dict(os.environ),
            "label": getattr(args, "label", None),
        }
        execute_mcp_request(self.name, port, payload, format)


class ListProcessesTool(ITool):
    name = "list"
    cli_description = "List all managed processes and their status"
    mcp_description = "List all managed processes and their status"

    @staticmethod
    def _apply(process_manager: ProcessManager) -> ListProcessesResult:
        """List all managed processes and their status."""
        logger.debug("list called")
        return process_manager.list()

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def list() -> ListProcessesResult:
            return self._apply(process_manager)

        mcp.add_tool(
            FunctionTool.from_function(
                list, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        pass

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        execute_mcp_request(self.name, port, format=format)


class GetProcessStatusTool(ITool):
    name = "status"
    cli_description = "Get the detailed status of a specific process"
    mcp_description = "Get the detailed information about a specific process, including its PID, command, working directory, and status."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> ProcessStatusResult:
        """Get the detailed status of a specific process."""
        logger.debug(
            "status called for pid=%s, command_or_label=%s",
            pid,
            command_or_label,
        )
        return process_manager.get_status(
            pid=pid,
            command_or_label=command_or_label,
            working_directory=Path(working_directory) if working_directory else None,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def status(
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
        ) -> ProcessStatusResult:
            return self._apply(
                process_manager, pid, command_or_label, working_directory
            )

        mcp.add_tool(
            FunctionTool.from_function(
                status, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, or command to get status for.",
        )
        parser.add_argument("args", nargs="*", help="Arguments to the command")
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            args.target, args.args
        )
        payload = {
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
        }
        execute_mcp_request(self.name, port, payload, format)


class StopProcessTool(ITool):
    name = "stop"
    cli_description = "Stop a running process"
    mcp_description = "Stop a running process. Blocks until the process is stopped."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
        force: bool = False,
        label: str | None = None,
    ) -> StopProcessResult:
        """Stop a running process by its PID."""
        logger.info(
            "stop called for pid=%s command_or_label=%s cwd=%s force=%s",
            pid,
            command_or_label,
            working_directory,
            force,
        )
        return process_manager.stop(
            pid=pid,
            command_or_label=command_or_label,
            working_directory=(Path(working_directory) if working_directory else None),
            force=force,
            label=label,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def stop(
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
            force: bool = False,
            label: str | None = None,
        ) -> StopProcessResult:
            return self._apply(
                process_manager, pid, command_or_label, working_directory, force, label
            )

        mcp.add_tool(
            FunctionTool.from_function(
                stop, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, or command to stop.",
        )
        parser.add_argument("args", nargs="*", help="Arguments to the command")
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )
        parser.add_argument(
            "--force", action="store_true", help="Force stop the process."
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            args.target, args.args
        )
        payload = {
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
            "force": args.force,
        }
        execute_mcp_request(self.name, port, payload, format)


class RestartProcessTool(ITool):
    name = "restart"
    cli_description = "Stops a process and starts it again with the same arguments and working directory"
    mcp_description = "Stops a process and starts it again with the same arguments and working directory"

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
        label: str | None = None,
    ) -> RestartProcessResult:
        """Stops a process and starts it again with the same parameters."""
        logger.info(
            "restart called for pid=%s, command_or_label=%s, cwd=%s",
            pid,
            command_or_label,
            working_directory,
        )
        return process_manager.restart(
            pid=pid,
            command_or_label=command_or_label,
            working_directory=(Path(working_directory) if working_directory else None),
            label=label,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def restart(
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
            label: str | None = None,
        ) -> RestartProcessResult:
            return self._apply(
                process_manager, pid, command_or_label, working_directory, label
            )

        mcp.add_tool(
            FunctionTool.from_function(
                restart, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, or command to restart.",
        )
        # Remaining args will be parsed manually.
        parser.add_argument("args", nargs="*")
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            args.target, args.args
        )

        payload = {
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
        }
        execute_mcp_request(self.name, port, payload, format)


class GetProcessOutputTool(ITool):
    name = "output"
    cli_description = "Retrieve captured output from a process"
    mcp_description = "Retrieve captured output from a process. If no arguments are provided, the last 100 lines of the combined stdout+stderr output are returned."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        stream: StreamEnum = StreamEnum.combined,
        lines: int | None = 100,
        before_time: str | None = None,
        since_time: str | None = None,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> ProcessOutputResult:
        """Retrieve captured output from a process."""
        logger.debug(
            "output called pid=%s stream=%s lines=%s before=%s since=%s",
            pid,
            stream,
            lines,
            before_time,
            since_time,
        )
        return process_manager.get_output(
            pid=pid,
            stream=stream,
            lines=lines,
            before_time=before_time,
            since_time=since_time,
            command_or_label=command_or_label,
            working_directory=Path(working_directory) if working_directory else None,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def output(
            stream: StreamEnum = StreamEnum.combined,
            lines: int | None = 100,
            before_time: str | None = None,
            since_time: str | None = None,
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
        ) -> ProcessOutputResult:
            return self._apply(
                process_manager,
                stream,
                lines,
                before_time,
                since_time,
                pid,
                command_or_label,
                working_directory,
            )

        mcp.add_tool(
            FunctionTool.from_function(
                output, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, or command to get output for.",
        )
        parser.add_argument("args", nargs="*", help="Arguments to the command")
        parser.add_argument(
            "--stream",
            choices=["stdout", "stderr", "combined"],
            default="combined",
            help="The output stream to read.",
        )
        parser.add_argument(
            "--lines", type=int, help="The number of lines to retrieve."
        )
        parser.add_argument(
            "--before-time", help="Retrieve logs before this timestamp."
        )
        parser.add_argument("--since-time", help="Retrieve logs since this timestamp.")
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            args.target, args.args
        )

        payload = {
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
            "stream": args.stream,
            "lines": args.lines,
            "before_time": args.before_time,
            "since_time": args.since_time,
        }
        execute_mcp_request(self.name, port, payload, format)


class GetProcessLogPathsTool(ITool):
    name = "get_log_paths"
    cli_description = "Get the paths to the log files for a specific process"
    mcp_description = "Get the paths on the filesystem to the log files for a specific process. Usually you want 'output' instead."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> ProcessLogPathsResult:
        """Get the paths to the log files for a specific process."""
        logger.debug(
            "get_log_paths called for pid=%s, command_or_label=%s",
            pid,
            command_or_label,
        )
        return process_manager.get_log_paths(
            pid=pid,
            command_or_label=command_or_label,
            working_directory=Path(working_directory) if working_directory else None,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def get_log_paths(
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
        ) -> ProcessLogPathsResult:
            return self._apply(
                process_manager, pid, command_or_label, working_directory
            )

        mcp.add_tool(
            FunctionTool.from_function(
                get_log_paths, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, or command to get log paths for.",
        )
        parser.add_argument("args", nargs="*", help="Arguments to the command")
        parser.add_argument(
            "--working-directory",
            default=os.getcwd(),
            help="The working directory for the process.",
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            args.target, args.args
        )

        payload = {
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
        }
        execute_mcp_request(self.name, port, payload, format)


class KillPersistprocTool(ITool):
    name = "kill_persistproc"
    cli_description = (
        "Kill all managed processes and get the PID of the persistproc server"
    )
    mcp_description = (
        "Kill all managed processes and get the PID of the persistproc server"
    )

    @staticmethod
    def _apply(process_manager: ProcessManager) -> KillPersistprocResult:
        logger.debug("kill_persistproc called")
        return process_manager.kill_persistproc()

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def kill_persistproc() -> KillPersistprocResult:
            return self._apply(process_manager)

        mcp.add_tool(
            FunctionTool.from_function(
                kill_persistproc, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        pass

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        execute_mcp_request(self.name, port, format=format)


ALL_TOOL_CLASSES = [
    StartProcessTool,
    ListProcessesTool,
    GetProcessStatusTool,
    StopProcessTool,
    RestartProcessTool,
    GetProcessOutputTool,
    GetProcessLogPathsTool,
    KillPersistprocTool,
]
