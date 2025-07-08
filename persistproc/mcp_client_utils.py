from __future__ import annotations

import asyncio
import inspect
import json
import logging

from fastmcp.exceptions import ToolError

from .client import make_client
from .logging_utils import CLI_LOGGER
from .process_types import (
    ShutdownResult,
    ListProcessesResult,
    ProcessInfo,
    ProcessOutputResult,
    RestartProcessResult,
    StartProcessResult,
    StopProcessResult,
)
from .text_formatters import format_result

logger = logging.getLogger(__name__)


async def make_mcp_request(
    tool_name: str, port: int, payload: dict | None = None, format: str = "json"
) -> None:
    """Make a request to the MCP server and print the response."""
    payload = payload or {}

    async with make_client(port) as client:
        # Filter out None values from payload before sending
        json_payload = {k: v for k, v in payload.items() if v is not None}
        results = await client.call_tool(tool_name, json_payload)

        if not results:
            CLI_LOGGER.error(
                "No response from server for tool '%s'. Is the server running?",
                tool_name,
            )
            return

        # Result is a JSON string in the `text` attribute.
        result_data = json.loads(results[0].text)

        if format == "json":
            # Pretty-print JSON to stdout
            print(json.dumps(result_data, indent=2))
        else:
            # Format as human-readable text
            result_obj = _create_result_object(tool_name, result_data)
            if result_obj:
                formatted_text = format_result(result_obj)
                print(formatted_text)
            else:
                # Fallback to JSON if we don't recognize the tool
                print(json.dumps(result_data, indent=2))

        if result_data.get("error"):
            CLI_LOGGER.error(result_data["error"])


def _create_result_object(tool_name: str, result_data: dict) -> object | None:
    """Create a result object from JSON data based on the tool name."""

    # Map tool names to their result types
    result_type_map = {
        "start": StartProcessResult,
        "stop": StopProcessResult,
        "list": ListProcessesResult,
        "output": ProcessOutputResult,
        "restart": RestartProcessResult,
        "shutdown": ShutdownResult,
    }

    # Handle ctrl tool which can perform start/stop/restart actions
    if tool_name == "ctrl":
        action = result_data.get("action")
        if action == "start":
            result_type_map["ctrl"] = StartProcessResult
        elif action == "stop":
            result_type_map["ctrl"] = StopProcessResult
        elif action == "restart":
            result_type_map["ctrl"] = RestartProcessResult

    result_type = result_type_map.get(tool_name)
    if result_type:
        try:
            # Special handling for ListProcessesResult which contains ProcessInfo objects
            if result_type == ListProcessesResult:
                processes_data = result_data.get("processes", [])
                processes = []
                for proc_data in processes_data:
                    # Only include fields that ProcessInfo actually has
                    process_info = ProcessInfo(
                        pid=proc_data["pid"],
                        command=proc_data["command"],
                        working_directory=proc_data["working_directory"],
                        status=proc_data["status"],
                        label=proc_data["label"],
                    )
                    processes.append(process_info)
                return ListProcessesResult(processes=processes)
            else:
                # For other result types, filter out any fields not in the dataclass

                sig = inspect.signature(result_type)
                filtered_data = {
                    k: v for k, v in result_data.items() if k in sig.parameters
                }
                return result_type(**filtered_data)
        except Exception as e:
            logger.warning(f"Failed to create {result_type.__name__} from data: {e}")
            logger.debug(f"Data was: {result_data}")
            return None
    return None


def execute_mcp_request(
    tool_name: str, port: int, payload: dict | None = None, format: str = "json"
) -> None:
    """Execute an MCP request synchronously with error handling."""
    try:
        asyncio.run(make_mcp_request(tool_name, port, payload, format))
    except ConnectionError:
        CLI_LOGGER.error(
            "Cannot connect to persistproc server on port %d. Start it with 'persistproc serve'.",
            port,
        )
    except ToolError as e:
        CLI_LOGGER.error(e)
    except Exception as e:
        # Check if this is an MCP tool error response
        error_str = str(e)
        # log the raw error to stderr
        logger.error(e)
        if error_str.startswith("Error calling tool"):
            # Extract the error message and output as JSON for tests
            error_msg = error_str.replace(f"Error calling tool '{tool_name}': ", "")
            error_response = {"error": error_msg}
            print(json.dumps(error_response, indent=2))
            CLI_LOGGER.error(error_msg)
        else:
            CLI_LOGGER.error(
                "Unexpected error while calling tool '%s': %s", tool_name, e
            )
            CLI_LOGGER.error(
                "Cannot reach persistproc server on port %d. Make sure it is running (`persistproc serve`) or specify the correct port with --port or PERSISTPROC_PORT.",
                port,
            )
