import asyncio
import signal
import sys
from pathlib import Path
import json
import pytest
from fastmcp.client import Client

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _launch_cli(host: str, port: str, *extra_args: str):
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "persistproc",
        "--host",
        host,
        "--port",
        port,
        *extra_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )


class TestCLIBehaviours:
    async def test_tail_auto_exit(self, live_server_url):
        host, port = live_server_url.split(":")[-2].strip("/"), live_server_url.split(
            ":"
        )[-1].strip("/")
        script_path = (
            Path(__file__).parent.parent / "support_scripts" / "count_print.py"
        )
        proc = await _launch_cli(host, port, sys.executable, str(script_path))
        try:
            await asyncio.wait_for(proc.wait(), timeout=6)
            assert proc.returncode == 0
            err = (await proc.stderr.read()).decode()
            assert "has exited" in err
        finally:
            if proc.returncode is None:
                proc.terminate()
                await proc.wait()

    async def test_ctrl_c_detach(self, live_server_url):
        host, port = live_server_url.split(":")[-2].strip("/"), live_server_url.split(
            ":"
        )[-1].strip("/")
        command = "sleep 10"
        cli = await _launch_cli(host, port, *command.split())
        await asyncio.sleep(1)
        cli.send_signal(signal.SIGINT)
        if cli.stdin:
            cli.stdin.close()
        await asyncio.wait_for(cli.wait(), timeout=5)
        assert cli.returncode == 0
        stderr_out = (await cli.stderr.read()).decode()
        assert "Detaching from log tailing" in stderr_out
        client = Client(f"{live_server_url}/mcp/")
        async with client:
            procs = json.loads((await client.call_tool("list_processes", {}))[0].text)
            assert any(
                p["command"] == command and p["status"] == "running" for p in procs
            )
            pid = next(p["pid"] for p in procs if p["command"] == command)
            await client.call_tool("stop_process", {"pid": pid, "force": True})
