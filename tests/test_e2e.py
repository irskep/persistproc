import pytest
from tests.helpers import run_cli, extract_json, start_run, stop_run
from pathlib import Path
import time

COUNTER_SCRIPT = Path(__file__).parent / "scripts" / "counter.py"


def test_list_no_processes(server):
    """Test that the server runs and responds to a simple request."""
    proc = run_cli("list-processes")
    assert proc.returncode == 0
    assert extract_json(proc.stdout) == {"processes": []}


# ---------------------------------------------------------------------------
# New test – start a process, verify it appears, then stop it
# ---------------------------------------------------------------------------


def test_start_list_stop(server):
    """Start one process, ensure it runs, then stop it."""

    # 1. Start the counter script (runs indefinitely with --num-iterations 0).
    start_cmd = f"python {COUNTER_SCRIPT} --num-iterations 0"
    start = run_cli("start-process", start_cmd)
    data = extract_json(start.stdout)
    pid = data["pid"]

    # 2. Confirm it appears in the list and is running.
    listed = run_cli("list-processes")
    info = extract_json(listed.stdout)
    procs = info["processes"]
    match = next(p for p in procs if p["pid"] == pid)
    assert match["status"] == "running"

    # 3. Stop the process.
    stop = run_cli("stop-process", str(pid))
    extract_json(stop.stdout)  # ensure JSON present no error

    # 4. Verify it is no longer running (status != running).
    after = run_cli("list-processes")
    info_after = extract_json(after.stdout)
    match_after = next(p for p in info_after["processes"] if p["pid"] == pid)
    assert match_after["status"] != "running"


def test_process_restart(server):
    """Start a process, restart it, verify PID changes and remains running."""

    start_cmd = f"python {COUNTER_SCRIPT} --num-iterations 0"
    start = run_cli("start-process", start_cmd)
    data = extract_json(start.stdout)
    old_pid = data["pid"]

    # Restart the process.
    restart = run_cli("restart-process", str(old_pid))
    restart_info = extract_json(restart.stdout)
    new_pid = restart_info["pid"]

    assert new_pid != old_pid

    # Confirm only new process is running.
    listed = run_cli("list-processes")
    info = extract_json(listed.stdout)
    procs = info["processes"]

    # There should be exactly one entry with new_pid and status running.
    matches = [p for p in procs if p["pid"] == new_pid]
    assert len(matches) == 1
    assert matches[0]["status"] == "running"


def test_process_has_output(server):
    """Start a process, verify it has output, then stop it."""
    start_cmd = f"python {COUNTER_SCRIPT} --num-iterations 0"
    start = run_cli("start-process", start_cmd)
    data = extract_json(start.stdout)
    pid = data["pid"]

    time.sleep(1)

    # Get the output of the process.
    output = run_cli("get-process-output", str(pid), "stdout", "10")
    assert extract_json(output.stdout)["output"].startswith(["1", "3", "5", "7", "9"])

    # Stop the process.
    stop = run_cli("stop-process", str(pid))
    extract_json(stop.stdout)  # ensure JSON present no error


# ---------------------------------------------------------------------------
# Tests for `persistproc run`
# ---------------------------------------------------------------------------


def test_run_kills_process_on_exit(server):
    """`run` starts new process and stops it on Ctrl+C when --on-exit stop."""

    cmd_tokens = ["python", str(COUNTER_SCRIPT), "--num-iterations", "0"]
    run_proc = start_run(cmd_tokens, on_exit="stop")

    time.sleep(3)

    # Terminate run gracefully.
    stop_run(run_proc)

    # After run exits, there should be no running processes.
    listed = run_cli("list-processes")
    info = extract_json(listed.stdout)
    assert info["processes"] == []


def test_run_detach_keeps_process_running(server):
    """`run` with --on-exit detach leaves the managed process running."""

    # 1. Start `run` with `detach` and let it create a new process.
    cmd_tokens = ["python", str(COUNTER_SCRIPT), "--num-iterations", "0"]
    run_proc = start_run(cmd_tokens, on_exit="detach")

    # Give it a moment to start up and for the server to register it.
    time.sleep(3)

    # 2. Find the PID of the process managed by `run`.
    listed = run_cli("list-processes")
    info = extract_json(listed.stdout)
    procs = info["processes"]
    assert len(procs) == 1, "Expected exactly one process to be running"
    proc_dict = procs[0]
    assert proc_dict["status"] == "running"
    pid = proc_dict["pid"]

    # 3. Terminate the `run` command itself.
    stop_run(run_proc)

    # 4. Verify the managed process is still running because of `detach`.
    after = run_cli("list-processes")
    info_after = extract_json(after.stdout)
    proc_after = next((p for p in info_after["processes"] if p["pid"] == pid), None)

    assert (
        proc_after is not None
    ), f"Process with PID {pid} disappeared after run detached"
    assert proc_after["status"] == "running"

    # 5. Cleanup.
    run_cli("stop-process", str(pid))
