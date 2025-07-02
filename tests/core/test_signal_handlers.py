import signal
import sys
from unittest.mock import MagicMock

import pytest

from persistproc.core import ProcessManager, ProcessInfo

# We need the unpatched server module; tests/conftest.py patches
# setup_signal_handlers at session scope. Reloading restores it.
import importlib, persistproc.server as _pp_server

# Defer actual reference until inside tests to avoid redundant reloads
pp_server = _pp_server


@pytest.fixture
def pm_no_monitor(temp_dir, no_monitor_thread):
    """Provide a ProcessManager instance without its monitor thread."""
    return ProcessManager(temp_dir)


# ---------------------------------------------------------------------------
# Signal handler edge case – double Ctrl+C
# ---------------------------------------------------------------------------


def test_signal_handler_graceful_shutdown(pm_no_monitor, monkeypatch):
    """Verify that the custom SIGINT handler stops running processes and calls sys.exit."""

    # Reload server module to undo session-wide monkeypatch that replaced
    # setup_signal_handlers with a no-op in conftest.py fixtures.
    global pp_server
    pp_server = importlib.reload(pp_server)

    # Prepare a process manager with two running processes
    for pid in (100, 200):
        pm_no_monitor.processes[pid] = ProcessInfo(
            pid=pid,
            command="sleep 5",
            start_time="t",
            status="running",
            log_prefix=f"{pid}.sleep_5",
        )

    # Track stop_process calls
    pm_no_monitor.stop_process = MagicMock(return_value={})

    # Capture handler registration
    captured = {}

    def _capture_signal(sig, handler):
        captured[sig] = handler
        return None

    monkeypatch.setattr(signal, "signal", _capture_signal, raising=True)

    # Patch sys.exit so we can assert it is invoked
    exit_called = {}

    def _fake_exit(code=0):
        exit_called["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", _fake_exit, raising=True)

    # Register handlers (captured by our patched signal.signal)
    pp_server.setup_signal_handlers(pm_no_monitor)

    handler = captured.get(signal.SIGINT)
    assert handler is not None, "SIGINT handler was not registered"

    # Invoke handler manually
    with pytest.raises(SystemExit):
        handler(signal.SIGINT, None)

    # stop_process should have been called for each running process
    assert pm_no_monitor.stop_process.call_count == 2

    # sys.exit should have been invoked with code 0
    assert exit_called.get("code") == 0
