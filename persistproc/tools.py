"""
MCP tool implementations.

This module contains all the MCP tool functions that are exposed
by the persistproc server.
"""

import json
import logging

logger = logging.getLogger("persistproc")


def create_tools(app, process_manager):
    """Register all MCP tools with the FastMCP app."""

    @app.tool()
    def start_process(
        command: str, working_directory: str = None, environment: dict = None
    ) -> str:
        """Start a new long-running process."""
        logger.debug(f"start_process called with command: {command}")
        try:
            result = process_manager.start_process(
                command, working_directory, environment
            )
            logger.debug(f"start_process result: {result}")
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            logger.error(f"start_process error: {e}")
            return json.dumps({"error": str(e)})

    @app.tool()
    def stop_process(pid: int, force: bool = False) -> str:
        """Stop a running process by its PID."""
        logger.debug(f"stop_process called with pid: {pid}, force: {force}")
        try:
            result = process_manager.stop_process(pid, force)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def list_processes() -> str:
        """List all managed processes and their status."""
        logger.debug("list_processes called")
        try:
            result = process_manager.list_processes()
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_status(pid: int) -> str:
        """Get the detailed status of a specific process."""
        logger.debug(f"get_process_status called with pid: {pid}")
        try:
            result = process_manager.get_process_status(pid)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_output(
        pid: int,
        stream: str,
        lines: int = None,
        before_time: str = None,
        since_time: str = None,
    ) -> str:
        """
        Retrieve captured output from a process.
        Can fetch the last N lines, and/or lines before/since a given ISO8601 timestamp.
        Use PID 0 to retrieve the main persistproc server log; the 'stream' parameter is ignored in this case.
        """
        logger.debug(
            f"get_process_output called with pid: {pid}, stream: {stream}, lines: {lines}, before_time: {before_time}, since_time: {since_time}"
        )
        try:
            result = process_manager.get_process_output(
                pid, stream, lines, before_time, since_time
            )
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_log_paths(pid: int) -> str:
        """Get the paths to the log files for a specific process."""
        logger.debug(f"get_process_log_paths called with pid: {pid}")
        try:
            result = process_manager.get_log_paths(pid)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def restart_process(pid: int) -> str:
        """Stops a process and starts it again with the same parameters."""
        logger.debug(f"restart_process called with pid: {pid}")
        try:
            result = process_manager.restart_process(pid)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            logger.error(f"restart_process error: {e}")
            return json.dumps({"error": str(e)})
