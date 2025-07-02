import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastmcp.client import Client

from tests.integration.test_mcp_tools import call_json

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestCLIServerInteraction:
    async def test_cli_client_survives_restart(
        self, live_mcp_client: Client, live_server_url
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
            "--on-exit",
            "detach",
            *command_to_tail.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            target_process = None  # ensure defined even if never found
            list_res: list[dict] | None = None

            # Allow up to 30 s for the server to settle in extremely slow CI runs
            for _ in range(30):
                try:
                    list_res = await call_json(live_mcp_client, "list_processes", {})
                except Exception:
                    # Transient 5xx during FastMCP lifespan race – wait & retry
                    await asyncio.sleep(0.5)
                    continue

                target_process = next(
                    (
                        p
                        for p in list_res
                        if p["command"] == command_to_tail and p["status"] == "running"
                    ),
                    None,
                )
                if target_process:
                    break
                await asyncio.sleep(1)

            assert (
                target_process is not None
            ), f"Could not find the initial process running. Got: {list_res}"
            old_pid = target_process["pid"]

            # Use MCP to restart the process (simulating an agent action)
            restart_res = await call_json(
                live_mcp_client, "restart_process", {"pid": old_pid}
            )
            assert (
                "pid" in restart_res and restart_res["pid"] != old_pid
            ), f"Restart failed: {restart_res}"
            new_pid = restart_res["pid"]

            # Check the CLI client's output to see if it detected the restart
            output_found = False
            start_time = asyncio.get_event_loop().time()
            stderr_output = b""
            while asyncio.get_event_loop().time() - start_time < 20:
                try:
                    chunk = await asyncio.wait_for(
                        cli_process.stderr.read(1024), timeout=0.1
                    )
                    if not chunk:
                        break
                    stderr_output += chunk
                    if (
                        f"Process was restarted. Original PID was {old_pid}".encode()
                        in stderr_output
                    ):
                        output_found = True
                        break
                except asyncio.TimeoutError:
                    pass  # No new output, continue polling
                await asyncio.sleep(0.2)

            assert (
                output_found
            ), f"Did not find restart message in client stderr. Full output:\n{stderr_output.decode(errors='ignore')}"

        finally:
            # Clean up the subprocess
            if cli_process.returncode is None:
                cli_process.terminate()
                try:
                    await cli_process.wait()
                except ProcessLookupError:
                    # Process already exited; ignore for cleanup
                    pass

    async def test_cli_raw_tail(self, live_server_url):
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
            "--on-exit",
            "detach",
            *command_to_run.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Collect up to 60 lines (or ~20 s max) to account for slow startup
            raw_lines: list[str] = []
            for _ in range(60):
                try:
                    line = await asyncio.wait_for(
                        cli_proc.stdout.readline(), timeout=3.5
                    )
                except asyncio.TimeoutError:
                    # No data yet – continue polling until overall loop limit hit
                    continue

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
            try:
                cli_proc.terminate()
                await cli_proc.wait()
            except ProcessLookupError:
                # Process already exited; ignore for cleanup
                pass
