"""
Integration tests for MCP tools using a live server and the fastmcp client.
"""

import pytest
import pytest_asyncio
import sys
import time
import json
import re
import asyncio
import subprocess
from pathlib import Path

from fastmcp.client import Client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def call_json(client: Client, tool: str, args: dict):
    """Call a tool and return the parsed JSON payload."""
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


@pytest_asyncio.fixture
async def mcp_client(live_server_url):
    """Provides an initialized fastmcp Client for each test function."""
    client = Client(f"{live_server_url}/mcp/")
    async with client:
        yield client


class TestMCPToolsIntegration:
    """Test MCP tools against a live running server using the fastmcp client."""

    async def test_mcp_server_is_running(self, mcp_client: Client):
        """Test that the server is up and has the expected tools."""
        tools = await mcp_client.list_tools()
        tool_names = [t.name for t in tools]
        assert "start_process" in tool_names
        assert "list_processes" in tool_names

    async def test_start_and_list_process(self, mcp_client: Client):
        """Test starting a process and then listing it."""
        command = f"{sys.executable} -c \"import time; print('process started'); time.sleep(5)\""
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        assert start_res["status"] == "running"
        time.sleep(0.5)
        list_res = await call_json(mcp_client, "list_processes", {})
        assert any(p["pid"] == pid for p in list_res)

    async def test_get_process_status(self, mcp_client: Client):
        """Test getting the status of a specific process."""
        command = f'{sys.executable} -c "import time; time.sleep(2)"'
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        status_res = await call_json(mcp_client, "get_process_status", {"pid": pid})
        assert status_res["status"] == "running"

    async def test_stop_process(self, mcp_client: Client):
        """Test stopping a running process."""
        command = f'{sys.executable} -c "import time; time.sleep(5)"'
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        await call_json(mcp_client, "stop_process", {"pid": pid})
        time.sleep(1)
        final_status = await call_json(mcp_client, "get_process_status", {"pid": pid})
        assert final_status["status"] in ["exited", "stopped", "terminated"]

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

    async def test_get_process_logs(self, mcp_client: Client):
        """Test getting log paths and log content."""
        unique_output = f"unique_test_output_{time.time()}"
        command = f"{sys.executable} -c \"import sys, time; print('{unique_output}'); sys.stdout.flush(); time.sleep(1)\""
        start_res = await call_json(mcp_client, "start_process", {"command": command})
        pid = start_res["pid"]
        time.sleep(1)
        log_output = await call_json(
            mcp_client,
            "get_process_output",
            {"pid": pid, "stream": "stdout", "lines": 10},
        )
        assert unique_output in "".join(log_output)

    async def test_start_process_in_nonexistent_dir_fails(self, mcp_client: Client):
        """Test that starting a process in a bad directory fails."""
        bad_dir = "/path/to/some/dir/that/does/not/exist"
        res = await call_json(
            mcp_client,
            "start_process",
            {"command": "echo hello", "working_directory": bad_dir},
        )
        assert "error" in res and "does not exist" in res["error"]

    async def test_cli_client_survives_restart(
        self, mcp_client: Client, live_server_url
    ):
        """
        Test that the CLI client, when tailing a process, can correctly
        survive that process being restarted by another agent and
        continue tailing the new process.
        """
        host, port = live_server_url.split(":")[-2].strip("/"), live_server_url.split(
            ":"
        )[-1].strip("/")

        # Launch the CLI client as a separate process to tail the command
        # Use a simple command that is easy to identify
        command_to_tail = "sleep 30"

        cli_process = await asyncio.create_subprocess_exec(
            "python",
            "-m",
            "persistproc",
            "--host",
            host,
            "--port",
            port,
            *command_to_tail.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Wait for the client to start up and tail the initial process
            await asyncio.sleep(
                5
            )  # Increased sleep to ensure process starts and client is ready

            # Find the process PID via MCP
            list_res = await call_json(mcp_client, "list_processes", {})
            target_process = next(
                (p for p in list_res if p["command"] == command_to_tail), None
            )
            assert (
                target_process is not None
            ), f"Could not find the initial process running. Got: {list_res}"
            old_pid = target_process["pid"]

            # Use MCP to restart the process (simulating an agent action)
            restart_res = await call_json(
                mcp_client, "restart_process", {"pid": old_pid}
            )
            assert (
                "pid" in restart_res and restart_res["pid"] != old_pid
            ), f"Restart failed: {restart_res}"
            new_pid = restart_res["pid"]

            # Check the CLI client's output to see if it detected the restart
            output_found = False
            try:
                # Read stderr line-by-line to find the restart message
                for _ in range(40):  # Up to ~20 seconds
                    line = await asyncio.wait_for(
                        cli_process.stderr.readline(), timeout=1.0
                    )
                    if not line:
                        break
                    decoded_line = line.decode()
                    if f"restarted. Now tracking new PID {new_pid}" in decoded_line:
                        output_found = True
                        break
                    await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                pass  # The assertion below will handle the failure.

            assert output_found, "Did not find restart message in client stderr."

        finally:
            # Clean up the subprocess
            cli_process.terminate()
            await cli_process.wait()

    async def test_cli_raw_tail(self, mcp_client: Client, live_server_url):
        """Run CLI with --raw and verify timestamped output lines are emitted."""

        host, port = live_server_url.split(":")[-2].strip("/"), live_server_url.split(
            ":"
        )[-1].strip("/")

        script_path = (
            Path(__file__).parent.parent / "support_scripts" / "count_print.py"
        ).resolve()

        # Command that prints predictable lines
        command_to_run = f"python {script_path}"

        # Launch CLI client in raw mode
        cli_proc = await asyncio.create_subprocess_exec(
            "python",
            "-m",
            "persistproc",
            "--host",
            host,
            "--port",
            port,
            "--raw",
            *command_to_run.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Wait for some output
            raw_lines = []
            for _ in range(10):
                line = await asyncio.wait_for(cli_proc.stdout.readline(), timeout=3)
                if not line:
                    break
                decoded = line.decode()
                raw_lines.append(decoded)
                if "COUNT 0" in decoded:
                    break

            assert any(
                "COUNT 0" in l for l in raw_lines
            ), "Expected raw log output not received"

            # Raw lines should start with ISO timestamp
            import re, datetime

            ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.")
            assert any(ts_pattern.match(l) for l in raw_lines)
        finally:
            cli_proc.terminate()
            await cli_proc.wait()
