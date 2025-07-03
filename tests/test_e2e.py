import pytest
from tests.helpers import run_cli, extract_json
from pathlib import Path

COUNTER_SCRIPT = Path(__file__).parent / "scripts" / "counter.py"


def test_server_runs_and_responds(server):
    """Test that the server runs and responds to a simple request."""
    proc = run_cli("list-processes")
    assert proc.returncode == 0
    # With an empty list we expect a friendly message.
    assert "No processes running." in proc.stderr


# ---------------------------------------------------------------------------
# New test – start a process, verify it appears, then stop it
# ---------------------------------------------------------------------------


def test_process_lifecycle(server):
    """Start one process, ensure it runs, then stop it."""

    # 1. Start the counter script (runs indefinitely with --num-iterations 0).
    start_cmd = f"python {COUNTER_SCRIPT} --num-iterations 0"
    start = run_cli("start-process", start_cmd)
    data = extract_json(start.stderr)
    pid = data["pid"]

    # 2. Confirm it appears in the list and is running.
    listed = run_cli("list-processes")
    info = extract_json(listed.stderr)
    procs = info["processes"]
    match = next(p for p in procs if p["pid"] == pid)
    assert match["status"] == "running"

    # 3. Stop the process.
    stop = run_cli("stop-process", str(pid))
    extract_json(stop.stderr)  # ensure JSON present no error

    # 4. Verify it is no longer running (status != running).
    after = run_cli("list-processes")
    info_after = extract_json(after.stderr)
    match_after = next(p for p in info_after["processes"] if p["pid"] == pid)
    assert match_after["status"] != "running"


def test_process_restart(server):
    """Start a process, restart it, verify PID changes and remains running."""

    start_cmd = f"python {COUNTER_SCRIPT} --num-iterations 0"
    start = run_cli("start-process", start_cmd)
    data = extract_json(start.stderr)
    old_pid = data["pid"]

    # Restart the process.
    restart = run_cli("restart-process", str(old_pid))
    restart_info = extract_json(restart.stderr)
    new_pid = restart_info["pid"]

    assert new_pid != old_pid

    # Confirm only new process is running.
    listed = run_cli("list-processes")
    info = extract_json(listed.stderr)
    procs = info["processes"]

    # There should be exactly one entry with new_pid and status running.
    matches = [p for p in procs if p["pid"] == new_pid]
    assert len(matches) == 1
    assert matches[0]["status"] == "running"
