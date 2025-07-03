import pytest
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the *persistproc* CLI via the repository's helper script.

    Environment variables (*PERSISTPROC_…*) are assumed to have been set by the
    ``_persistproc_env`` fixture in *tests/conftest.py*.
    """

    # note that data dir and log path are set by the environment variables.
    cmd = ["python", "-m", "persistproc", "-vv", *args]
    # For short-lived CLI invocations we can run synchronously.
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def start_persistproc() -> subprocess.Popen[str]:
    """Start the persistproc server (background Popen)."""
    cmd = ["python", "-m", "persistproc", "-vv", "serve"]
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait until the server is ready.
    while True:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        if "Uvicorn running on" in line:
            break
    return proc


# fixture to get a running persistproc server
@pytest.fixture
def persistproc_server():
    """Start a persistproc server for the duration of one test."""
    server_proc = start_persistproc()
    yield server_proc
    server_proc.terminate()
    server_proc.wait(timeout=10)


# Alias fixture so tests can request `server` directly.
@pytest.fixture
def server(persistproc_server):
    return persistproc_server


# minimal test: list processes, there are none
# TODO: add fixture to get a running persistproc server
def test_server_runs_and_responds(server):
    """Test that the server runs and responds to a simple request."""
    proc = _run_cli("list-processes")
    assert proc.returncode == 0
    # With an empty list we expect a friendly message.
    assert "No processes running." in proc.stderr
