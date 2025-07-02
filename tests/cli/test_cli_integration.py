import asyncio
import signal
import sys
from pathlib import Path
import json
import pytest
from fastmcp.client import Client
import httpx
from typing import Optional

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _launch_cli(
    host: str, port: str, *extra_args: str, on_exit: Optional[str] = "detach"
):
    """Helper to start the persistproc CLI as subprocess, returns process handle."""
    cli_args = [
        sys.executable,
        "-m",
        "persistproc",
        "--host",
        host,
        "--port",
        port,
        "-v",  # Run in verbose mode for more informative test logs
        "run",  # Explicitly use the 'run' subcommand *after* global options
    ]
    if on_exit:
        cli_args.extend(["--on-exit", on_exit])

    cli_args.extend(extra_args)

    return await asyncio.create_subprocess_exec(
        *cli_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )


class TestCLIBehaviours:
    async def test_tail_auto_exit(self, live_server_url):
        """CLI should terminate automatically when the process exits (non-raw mode)."""
        host, port = live_server_url.split(":")[-2].strip("/"), live_server_url.split(
            ":"
        )[-1].strip("/")

        script_path = (
            Path(__file__).parent.parent / "support_scripts" / "count_print.py"
        ).resolve()
        proc = await _launch_cli(
            host, port, sys.executable, str(script_path), on_exit="detach"
        )

        try:
            # Allow some time for the child process to finish
            await asyncio.sleep(2)

            # Manually trigger detach
            proc.send_signal(signal.SIGINT)

            await asyncio.wait_for(proc.wait(), timeout=10)
            assert proc.returncode == 0
            err = (await proc.stderr.read()).decode()
            assert "Detaching from" in err
        finally:
            if proc.returncode is None:
                proc.terminate()
                await proc.wait()

    async def test_cli_ctrl_c_detaches_and_leaves_process_running(
        self, live_server_url
    ):
        host, port_str = live_server_url.split(":")[-2:]
        port = int(port_str.strip("/"))
        host = host.split(":")[-1].strip("/")
        command = ["sleep", "10"]
        cli = None
        try:
            cli = await _launch_cli(host, str(port), *command, on_exit="detach")

            try:
                while True:
                    line = await asyncio.wait_for(cli.stderr.readline(), timeout=5)
                    if not line:
                        pytest.fail("CLI exited prematurely without starting process.")
                    if b"Starting process" in line or b"already running" in line:
                        break
            except asyncio.TimeoutError:
                pytest.fail("Timed out waiting for CLI to start the process.")

            cli.send_signal(signal.SIGINT)
            if cli.stdin:
                cli.stdin.close()
            await asyncio.wait_for(cli.wait(), timeout=5)
            assert cli.returncode == 0
            stderr_out = (await cli.stderr.read()).decode()
            assert "Detaching from" in stderr_out
            client = Client(f"{live_server_url}/mcp/")
            try:
                async with client:
                    procs = json.loads(
                        (await client.call_tool("list_processes", {}))[0].text
                    )
                    assert any(
                        p["command"] == " ".join(command) and p["status"] == "running"
                        for p in procs
                    )
                    pid = next(
                        p["pid"] for p in procs if p["command"] == " ".join(command)
                    )
                    await client.call_tool("stop_process", {"pid": pid, "force": True})
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 500:
                    raise
            except httpx.ConnectError:
                pass
        finally:
            if cli and cli.returncode is None:
                cli.terminate()
                await cli.wait()
