import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def temp_dir():
    """Provides a temporary directory that's cleaned up after the test."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_app_data_dir(temp_dir, monkeypatch):
    """Mocks the APP_DATA_DIR to use a temporary directory."""
    # These constants are now computed dynamically in utils.py
    # No need to patch them directly
    return temp_dir


@pytest.fixture
def mock_subprocess():
    """Provides a mock subprocess.Popen that doesn't actually start processes."""
    with patch("persistproc.core.subprocess.Popen") as mock_popen:
        mock_proc = Mock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Process is running
        mock_proc.stdout = Mock()
        mock_proc.stderr = Mock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""
        mock_popen.return_value = mock_proc
        yield mock_popen, mock_proc


@pytest.fixture
def sample_command():
    """Provides a sample command string for testing."""
    return "echo hello world"


@pytest.fixture
def mock_process_info():
    """Provides sample ProcessInfo data for testing."""
    from persistproc.core import ProcessInfo

    return ProcessInfo(
        pid=12345,
        command="echo hello",
        start_time="2023-01-01T12:00:00.000Z",
        status="running",
        log_prefix="12345.echo_hello",
        working_directory="/tmp",
        environment={"TEST": "value"},
    )


@pytest.fixture
def no_monitor_thread():
    """Prevents the ProcessManager monitor thread from starting during tests."""
    with patch("persistproc.core.ProcessManager._monitor_processes"):
        yield


@pytest.fixture
def mock_killpg():
    """Mocks process killing to prevent actual signal sending during tests."""
    # Mock both Unix and Windows process killing
    with (
        patch("persistproc.core.os.killpg") as mock_kill_unix,
        patch("persistproc.core.subprocess.run") as mock_subprocess_run,
    ):
        yield mock_kill_unix


@pytest.fixture
def mock_getpgid():
    """Mocks os.getpgid to return a predictable process group ID."""
    with patch("persistproc.core.os.getpgid", return_value=12345) as mock_getpgid:
        yield mock_getpgid


class MockServer:
    """A mock MCP server for testing."""

    def __init__(self):
        self.tools = {}
        self.running = False

    def tool(self, name=None):
        def decorator(func):
            tool_name = name or func.__name__
            self.tools[tool_name] = func
            return func

        return decorator

    def run(self, **kwargs):
        self.running = True
        # Simulate server running briefly
        time.sleep(0.1)


@pytest.fixture
def mock_mcp_server():
    """Provides a mock MCP server for testing."""
    return MockServer()
