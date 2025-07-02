import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch
import socket
import uvicorn
from persistproc.server import create_app, run_server
from persistproc.utils import get_app_data_dir
import persistproc.server
from fastmcp.client import Client

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def free_port():
    """Finds a free port for the test server to listen on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url(free_port, temp_dir_session, monkeypatch_session):
    """Starts a live server in a thread and provides its URL."""

    monkeypatch_session.setattr(
        "persistproc.server.get_app_data_dir", lambda name: temp_dir_session
    )
    # Prevent signal handlers from being set up in the test thread
    monkeypatch_session.setattr(
        "persistproc.server.setup_signal_handlers", lambda: None
    )

    server_thread = threading.Thread(
        target=run_server,
        kwargs={"host": "127.0.0.1", "port": free_port},
        daemon=True,
    )
    server_thread.start()

    # Poll the server to wait for it to be ready
    start_time = time.time()
    while time.time() - start_time < 10:  # 10-second timeout
        try:
            with socket.create_connection(("127.0.0.1", free_port), timeout=0.1):
                break
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(0.1)
    else:
        pytest.fail("Server did not start within 10 seconds.")

    # Wait for the process_manager to be initialized
    while persistproc.server.process_manager is None:
        time.sleep(0.1)

    # Ensure monitor thread is stopped after tests
    yield f"http://127.0.0.1:{free_port}"
    persistproc.server.process_manager.stop_monitor_thread()


@pytest.fixture(scope="session")
def temp_dir_session():
    """Provides a temporary directory for the whole test session."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture
def temp_dir(temp_dir_session):
    """Provides a temporary directory that's cleaned up after the test."""
    temp_path = Path(tempfile.mkdtemp(dir=temp_dir_session))
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def process_manager(temp_dir):
    """Provides a ProcessManager instance for testing."""
    from persistproc.core import ProcessManager

    with patch("persistproc.core.ProcessManager._monitor_processes"):
        pm = ProcessManager(log_directory=temp_dir)
        yield pm
        pm.stop_monitor_thread()


@pytest.fixture
def mcp_server(process_manager):
    """Provides an in-memory MCP server instance for testing."""
    with patch("persistproc.server.setup_signal_handlers", lambda: None):
        app = create_app(process_manager)
        return app


@pytest_asyncio.fixture
async def live_mcp_client(live_server_url):
    """Provides a client connected to the live test server."""
    client = Client(f"{live_server_url}/mcp/")
    async with client:
        yield client


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
    """Mocks Unix process killing."""
    with (
        patch("persistproc.core.os.killpg") as mock_kill_unix,
        patch("persistproc.core.os.getpgid", return_value=12345) as mock_getpgid,
    ):
        yield {
            "unix_kill": mock_kill_unix,
            "getpgid": mock_getpgid,
        }


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
