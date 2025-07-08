"""Shutdown persistproc server functionality."""

import asyncio
import json
import os
import signal

from .client import make_client
from .logging_utils import CLI_LOGGER
from .process_types import ShutdownResult
from .text_formatters import format_result

__all__ = ["shutdown_server"]


def shutdown_server(port: int, format_output: str = "text") -> None:
    """Shutdown the persistproc server by finding the process listening on the port and sending SIGINT."""
    try:
        # First verify server is running by connecting to it
        try:

            async def verify_server():
                async with make_client(port) as client:
                    results = await client.call_tool("list", {})
                    return results is not None

            if not asyncio.run(verify_server()):
                error_result = ShutdownResult(
                    error="Cannot connect to persistproc server - it may not be running"
                )
                _output_result(error_result, format_output)
                return
        except Exception:
            error_result = ShutdownResult(
                error="Cannot connect to persistproc server - it may not be running"
            )
            _output_result(error_result, format_output)
            return

        # Find the server process by using the 'list' tool with pid=0
        # This returns the server info in an OS-independent way
        try:

            async def get_server_info():
                async with make_client(port) as client:
                    results = await client.call_tool("list", {"pid": 0})
                    if not results:
                        return None
                    return json.loads(results[0].text)

            list_data = asyncio.run(get_server_info())
            if list_data is None:
                error_result = ShutdownResult(
                    error="No response from server for list tool"
                )
                _output_result(error_result, format_output)
                return

            if "processes" not in list_data or not list_data["processes"]:
                error_result = ShutdownResult(
                    error="Server process not found in list response"
                )
                _output_result(error_result, format_output)
                return

            server_process = list_data["processes"][0]
            server_pid = server_process.get("pid")
            if not isinstance(server_pid, int) or server_pid <= 0:
                error_result = ShutdownResult(error=f"Invalid server PID: {server_pid}")
                _output_result(error_result, format_output)
                return

        except Exception as e:
            error_result = ShutdownResult(error=f"Failed to get server PID: {e}")
            _output_result(error_result, format_output)
            return

        # Send SIGINT to the server process
        CLI_LOGGER.info("Sending SIGINT to persistproc server (PID %d)", server_pid)
        os.kill(server_pid, signal.SIGINT)

        # Output the result
        success_result = ShutdownResult(pid=server_pid)
        _output_result(success_result, format_output)

    except ProcessLookupError:
        error_result = ShutdownResult(
            error=f"Server process (PID {server_pid}) not found - it may have already exited"
        )
        _output_result(error_result, format_output)
    except PermissionError:
        error_result = ShutdownResult(
            error=f"Permission denied when trying to signal server process (PID {server_pid})"
        )
        _output_result(error_result, format_output)
    except Exception as e:
        error_result = ShutdownResult(error=f"Unexpected error: {e}")
        _output_result(error_result, format_output)


def _output_result(result: ShutdownResult, format_output: str) -> None:
    """Output the result in the requested format."""
    if format_output == "json":
        if result.error:
            print(json.dumps({"error": result.error}))
        else:
            print(json.dumps({"pid": result.pid}))
    else:
        # Use text formatter
        print(format_result(result))
