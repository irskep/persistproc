"""Kill persistproc server functionality."""

import json
import os
import signal

from .logging_utils import CLI_LOGGER
from .mcp_client_utils import execute_mcp_request
from .process_types import KillPersistprocResult
from .text_formatters import format_result

__all__ = ["kill_persistproc_server"]


def kill_persistproc_server(port: int, format_output: str = "text") -> None:
    """Kill the persistproc server by finding the process listening on the port and sending SIGINT."""
    try:
        # First verify server is running by connecting to it
        try:
            execute_mcp_request("list", port, {}, "json")
        except Exception:
            error_result = KillPersistprocResult(
                error="Cannot connect to persistproc server - it may not be running"
            )
            _output_result(error_result, format_output)
            return

        # Find the server process by using the 'list' tool with pid=0
        # This returns the server info in an OS-independent way
        try:
            list_response = execute_mcp_request("list", port, {"pid": 0}, "json")
            list_data = (
                json.loads(list_response)
                if isinstance(list_response, str)
                else list_response
            )

            if "processes" not in list_data or not list_data["processes"]:
                error_result = KillPersistprocResult(
                    error="Server process not found in list response"
                )
                _output_result(error_result, format_output)
                return

            server_process = list_data["processes"][0]
            server_pid = server_process.get("pid")
            if not isinstance(server_pid, int) or server_pid <= 0:
                error_result = KillPersistprocResult(
                    error=f"Invalid server PID: {server_pid}"
                )
                _output_result(error_result, format_output)
                return

        except Exception as e:
            error_result = KillPersistprocResult(error=f"Failed to get server PID: {e}")
            _output_result(error_result, format_output)
            return

        # Send SIGINT to the server process
        CLI_LOGGER.info("Sending SIGINT to persistproc server (PID %d)", server_pid)
        os.kill(server_pid, signal.SIGINT)

        # Output the result
        success_result = KillPersistprocResult(pid=server_pid)
        _output_result(success_result, format_output)

    except ProcessLookupError:
        error_result = KillPersistprocResult(
            error=f"Server process (PID {server_pid}) not found - it may have already exited"
        )
        _output_result(error_result, format_output)
    except PermissionError:
        error_result = KillPersistprocResult(
            error=f"Permission denied when trying to signal server process (PID {server_pid})"
        )
        _output_result(error_result, format_output)
    except Exception as e:
        error_result = KillPersistprocResult(error=f"Unexpected error: {e}")
        _output_result(error_result, format_output)


def _output_result(result: KillPersistprocResult, format_output: str) -> None:
    """Output the result in the requested format."""
    if format_output == "json":
        if result.error:
            print(json.dumps({"error": result.error}))
        else:
            print(json.dumps({"pid": result.pid}))
    else:
        # Use text formatter
        print(format_result(result))
