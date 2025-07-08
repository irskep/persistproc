from __future__ import annotations

import abc
import json
import os
import shlex
from argparse import ArgumentParser, Namespace
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from persistproc.process_manager import ProcessManager

from .mcp_client_utils import execute_mcp_request
from .process_types import (
    ListProcessesResult,
    ProcessControlResult,
    ProcessOutputResult,
    StreamEnum,
)

import logging

# WARNING: run.py depends on details of this file in ways that the linter and
# type checker cannot detect! Specifically tool names, parameters, and return types.

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


class ListProcessesTool(ITool):
    name = "list"
    cli_description = "List all managed processes and their status, optionally filtered by pid, command, or working directory"
    mcp_description = "List all managed processes and their status. Can optionally filter by pid, command_or_label, or working_directory. Returns detailed information including log paths for each process."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> ListProcessesResult:
        """List all managed processes and their status, optionally filtered."""
        logger.debug(
            "list called with pid=%s, command_or_label=%s, working_directory=%s",
            pid,
            command_or_label,
            working_directory,
        )
        return process_manager.list(
            pid=pid,
            command_or_label=command_or_label,
            working_directory=working_directory,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def list(
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
        ) -> ListProcessesResult:
            return self._apply(
                process_manager, pid, command_or_label, working_directory
            )

        mcp.add_tool(
            FunctionTool.from_function(
                list, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--pid",
            type=int,
            help="Filter by process ID",
        )
        parser.add_argument(
            "--command-or-label",
            type=str,
            help="Filter by command or label",
        )
        parser.add_argument(
            "--working-directory",
            type=str,
            help="Filter by working directory",
        )

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        payload = {}
        if getattr(args, "pid", None) is not None:
            payload["pid"] = args.pid
        if getattr(args, "command_or_label", None) is not None:
            payload["command_or_label"] = args.command_or_label
        if getattr(args, "working_directory", None) is not None:
            payload["working_directory"] = args.working_directory

        if payload:
            execute_mcp_request(self.name, port, payload, format)
        else:
            execute_mcp_request(self.name, port, format=format)


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


class CtrlProcessTool(ITool):
    name = "ctrl"
    cli_description = "Unified process control: start, stop, or restart processes"
    mcp_description = "Unified process control command that can start, stop, or restart processes. Supports all the parameters of individual commands with action-based dispatch."

    @staticmethod
    def _apply(
        process_manager: ProcessManager,
        action: str,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
        force: bool = False,
        label: str | None = None,
    ) -> ProcessControlResult:
        """Unified process control method."""
        logger.info(
            "ctrl called – action=%s, pid=%s, command_or_label=%s, working_directory=%s",
            action,
            pid,
            command_or_label,
            working_directory,
        )
        return process_manager.ctrl(
            action=action,
            pid=pid,
            command_or_label=command_or_label,
            working_directory=working_directory,
            environment=environment,
            force=force,
            label=label,
        )

    def register_tool(self, process_manager: ProcessManager, mcp: FastMCP) -> None:
        def ctrl(
            action: str,
            pid: int | None = None,
            command_or_label: str | None = None,
            working_directory: str | None = None,
            environment: dict[str, str] | None = None,
            force: bool = False,
            label: str | None = None,
        ) -> ProcessControlResult:
            return self._apply(
                process_manager,
                action,
                pid,
                command_or_label,
                working_directory,
                environment,
                force,
                label,
            )

        mcp.add_tool(
            FunctionTool.from_function(
                ctrl, name=self.name, description=self.mcp_description
            )
        )

    def build_subparser(self, parser: ArgumentParser) -> None:
        # Options must come first to avoid conflicts with command arguments
        parser.add_argument(
            "--working-directory",
            help="The working directory for the process (required for start, optional for stop/restart)",
        )
        parser.add_argument(
            "--environment",
            type=str,
            help="Environment variables as JSON string (start only)",
        )
        parser.add_argument(
            "--force", action="store_true", help="Force stop the process (stop only)"
        )
        parser.add_argument(
            "--label",
            type=str,
            help="Custom label for the process",
        )
        # Positional arguments come last
        parser.add_argument(
            "action",
            choices=["start", "stop", "restart"],
            help="The action to perform: start, stop, or restart",
        )
        parser.add_argument(
            "target",
            metavar="TARGET",
            help="The PID, label, command, or command to start (depending on action)",
        )
        parser.add_argument("args", nargs="*", help="Arguments to the command")

    def call_with_args(self, args: Namespace, port: int, format: str = "json") -> None:
        pid = None
        command_or_label = None
        action = None

        # Detect if we were called via backwards compatibility alias
        if hasattr(args, "command_") and hasattr(args, "target"):
            # This means we have both command_ and target, which shouldn't happen in normal ctrl usage
            # This indicates a backwards compatibility argument structure issue
            print("Error: Conflicting argument structure detected")
            return
        elif hasattr(args, "command_"):
            # Backwards compatibility: start command
            action = "start"
            if args.working_directory is None:
                args.working_directory = os.getcwd()

            # Construct command string from command_ and args
            if args.args:
                command_or_label = shlex.join([args.command_] + args.args)
            else:
                command_or_label = args.command_
        elif hasattr(args, "target") and not hasattr(args, "action"):
            # Backwards compatibility: stop/restart command
            # Need to determine action from args.command (which is the CLI command name)
            command_name = getattr(args, "command", "unknown")
            if command_name in ["stop", "restart"]:
                action = command_name
            else:
                print(f"Error: Unknown backwards compatibility command: {command_name}")
                return

            # Parse target - could be PID or command with args
            pid, command_or_label = _parse_target_to_pid_or_command_or_label(
                args.target, args.args
            )
            if pid is not None:
                # If it's a PID, don't use command_or_label
                command_or_label = None
            elif args.args:
                command_or_label = shlex.join([args.target] + args.args)
            else:
                command_or_label = args.target
        else:
            # Normal ctrl command handling
            action = args.action

            # Parse target and args based on action
            if action == "start":
                # For start, target is the command and we need working directory
                if args.target is None:
                    print("Error: TARGET (command) is required for start action")
                    return
                if args.working_directory is None:
                    # Default to current directory
                    args.working_directory = os.getcwd()

                # Construct command string from target and args
                if args.args:
                    command_or_label = shlex.join([args.target] + args.args)
                else:
                    command_or_label = args.target
            else:
                # For stop/restart, target can be PID or command/label
                if args.target is None:
                    print(f"Error: TARGET is required for {action} action")
                    return

                # Parse target - could be PID or command with args
                pid, command_or_label = _parse_target_to_pid_or_command_or_label(
                    args.target, args.args
                )
                if pid is not None:
                    # If it's a PID, don't use command_or_label
                    command_or_label = None
                # If we have a command with multiple words, join them
                elif args.args:
                    command_or_label = shlex.join([args.target] + args.args)
                else:
                    command_or_label = args.target

        # Parse environment if provided
        environment = None
        if getattr(args, "environment", None):
            try:
                environment = json.loads(args.environment)
            except json.JSONDecodeError as e:
                print(f"Error parsing environment JSON: {e}")
                return

        payload = {
            "action": action,
            "pid": pid,
            "command_or_label": command_or_label,
            "working_directory": args.working_directory,
            "environment": environment,
            "force": getattr(args, "force", False),
            "label": getattr(args, "label", None),
        }

        execute_mcp_request(self.name, port, payload, format)


ALL_TOOL_CLASSES = [
    CtrlProcessTool,
    ListProcessesTool,
    GetProcessOutputTool,
]
