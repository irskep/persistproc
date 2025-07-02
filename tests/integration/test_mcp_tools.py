"""
Integration tests for MCP tools using a live server and the fastmcp client.
"""

import pytest
import sys
import time
import json
import re
import asyncio
import subprocess
from pathlib import Path
import httpx
import pytest_asyncio

from fastmcp.client import Client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def mcp_client(mcp_server):
    """Provides an initialized fastmcp Client for each test function, using an in-memory server."""
    async with Client(mcp_server) as client:
        yield client


async def call_json(client: Client, tool: str, args: dict):
    """Call a tool and return the parsed JSON payload."""
    import httpx, asyncio

    last_exc: Exception | None = None
    base_url = client.transport.base_url if hasattr(client.transport, "base_url") else None  # type: ignore
    for _ in range(12):
        try:
            res = await client.call_tool(tool, args)
            # fastmcp returns a list of Content objects; handle that
            if isinstance(res, list):
                if not res:
                    return None
                first = res[0]
                if hasattr(first, "text"):
                    return json.loads(first.text)
                return first
            return res
        except httpx.HTTPStatusError as e:
            # Retry transient 5xx errors stemming from FastMCP lifespan race conditions
            if e.response.status_code >= 500:
                last_exc = e
                await asyncio.sleep(0.3)
                continue
            raise
        except RuntimeError as e:
            # fastmcp raises this when the underlying HTTP session got closed after a 500
            if "Client is not connected" in str(e) and base_url is not None:
                last_exc = e
                try:
                    await client._connect()
                except Exception:
                    # If reconnect fails, recreate client object as last resort
                    if base_url is not None:
                        client = Client(base_url)
                        await client.__aenter__()  # type: ignore[misc]
                await asyncio.sleep(0.3)
                continue
    # Retries exhausted – re-raise last exception if present, else generic RuntimeError
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("call_json retries exhausted without response")


class TestMCPToolsIntegration:
    """Test MCP tools against a live running server using the fastmcp client."""

    async def test_mcp_server_is_running(self, mcp_client: Client):
        """Check that the MCP server is running and has registered tools."""
        tools = await mcp_client.list_tools()
        assert "start_process" in [t.name for t in tools]

    async def test_start_and_list_process(self, mcp_client: Client):
        """Test starting a process and then listing it."""
        command = f"{sys.executable} -c \"import time; print('process started'); time.sleep(5)\""
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        assert start_res["status"] == "running"
        time.sleep(0.5)
        list_res = await call_json(mcp_client, "list_processes", {})
        assert any(
            p["command"] == command and p["status"] == "running" for p in list_res
        )

    async def test_get_process_status(self, mcp_client: Client):
        """Test getting the status of a specific process."""
        command = f'{sys.executable} -c "import time; time.sleep(2)"'
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        status_res = await call_json(mcp_client, "get_process_status", {"pid": pid})
        assert status_res["pid"] == pid
        assert status_res["status"] == "running"

    async def test_stop_process(self, mcp_client: Client):
        """Test stopping a running process."""
        command = f'{sys.executable} -c "import time; time.sleep(5)"'
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        await call_json(mcp_client, "stop_process", {"pid": pid})
        time.sleep(1)
        final_status = await call_json(mcp_client, "get_process_status", {"pid": pid})
        assert final_status["status"] == "terminated"
        assert "exit_code" in final_status

    async def test_restart_process(self, mcp_client: Client):
        """Test restarting a process."""
        command = f'{sys.executable} -c "import time; time.sleep(2)"'
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        if "error" in start_res and "is already running" in start_res["error"]:
            old_pid = int(re.search(r"PID (\d+)", start_res["error"]).group(1))
        else:
            old_pid = start_res["pid"]
        time.sleep(0.5)
        restart_res = await call_json(mcp_client, "restart_process", {"pid": old_pid})
        new_pid = restart_res["pid"]
        assert new_pid != old_pid
        assert "running" in restart_res["status"]

    async def test_get_process_logs(self, mcp_client: Client, mcp_server):
        """Test getting log paths and log content."""
        unique_output = f"output_{time.time()}"
        command = f"{sys.executable} -c \"import sys, time; print('{unique_output}'); sys.stdout.flush(); time.sleep(1)\""
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]

        # In in-memory tests, the monitor thread is patched out, so we manually log an event
        # to ensure the log file contains system messages for the test to find.
        mcp_server.process_manager._log_event(
            mcp_server.process_manager.processes[pid], "Test system event"
        )

        time.sleep(1)
        log_output = await call_json(
            mcp_client,
            "get_process_output",
            {"pid": pid, "stream": "combined", "lines": 10},
        )
        assert any(unique_output in line for line in log_output)
        assert any("SYSTEM" in line for line in log_output)

    async def test_start_process_in_nonexistent_dir_fails(self, mcp_client: Client):
        """Test that starting a process in a bad directory fails."""
        bad_dir = "/path/to/some/dir/that/does/not/exist"
        res = await call_json(
            mcp_client,
            "start_process",
            {"command": "echo hello", "working_directory": bad_dir},
        )
        assert "error" in res and "does not exist" in res["error"]

    # The following tests require a live server to interact with the CLI,
    # so they are moved to a separate file.
