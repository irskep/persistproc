import subprocess
import sys
import time
import re
from pathlib import Path

import pytest


# -----------------------------------------------------------------------------
# Small helpers – *minimal* implementations so the test can run without relying
# on yet-to-be-written utilities.  In future these can be replaced with the full
# versions outlined in the design docs.
# -----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_IN_VENV = PROJECT_ROOT / "run-in-venv.sh"


def _run_cli(data_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Execute *persistproc* via the repository's `run-in-venv.sh` helper."""

    cmd = [
        str(RUN_IN_VENV),
        "python",
        "-m",
        "persistproc",
        *args,
        "--data-dir",
        str(data_dir),
    ]
    # Capture *both* stdout and stderr as text for assertions/debugging.
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _latest_log_file(data_dir: Path) -> Path | None:
    """Return the most recent *persistproc.run.*.log* file in *data_dir*."""
    log_files = sorted(data_dir.glob("persistproc.run.*.log"))
    return log_files[-1] if log_files else None


def _wait_for_log_line(
    data_dir: Path, pattern: str, timeout: float = 5.0, interval: float = 0.1
) -> str:
    """Poll the log file for *pattern* until *timeout* seconds have passed.

    Returns the matching line or raises *pytest.TimeoutError*.
    """
    deadline = time.time() + timeout
    compiled = re.compile(pattern)

    while time.time() < deadline:
        log_path = _latest_log_file(data_dir)
        if log_path and log_path.exists():
            with log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if compiled.search(line):
                        return line.rstrip("\n")
        time.sleep(interval)

    pytest.fail(f"Pattern {pattern!r} not found in log within {timeout} seconds")


# -----------------------------------------------------------------------------
# Implemented smoke test
# -----------------------------------------------------------------------------


def test_serve_command_writes_startup_log(tmp_path: Path):
    """`persistproc serve` should emit a startup INFO log entry."""

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # The serve stub returns immediately.
    result = _run_cli(data_dir, "serve", "--port", "9999")

    assert result.returncode == 0, result.stderr

    # Confirm the expected log entry is written.
    matched_line = _wait_for_log_line(
        data_dir,
        r"Starting MCP server on http://127\.0\.0\.1:9999",
    )

    assert "MCP server" in matched_line


# -----------------------------------------------------------------------------
# Additional tests (enumerated, not implemented yet)
# -----------------------------------------------------------------------------
# 1. test_start_and_stop_process_roundtrip
#        – Ensure *start_process* launches a long-running command, it appears in
#          *list_processes*, *get_process_status* returns "running", then
#          *stop_process* cleanly terminates it (exit_code == 0) and the process
#          disappears from the list.
#
# 2. test_restart_process_preserves_command_and_changes_pid
#        – Start a process, capture its `command` and `pid`, call
#          *restart_process*, verify a new PID is assigned while the command
#          remains identical.
#
# 3. test_get_process_output_streams
#        – Run a helper script that writes distinct text to *stdout* and
#          *stderr*; assert that *get_process_output* retrieves the correct
#          lines for each stream.
#
# 4. test_run_convenience_tails_output
#        – Invoke `persistproc run python -c "print('hello')"` and assert the
#          printed text is visible on *stdout* and the exit code is propagated.
#
# 5. test_data_dir_flag_respected
#        – Pass a custom `--data-dir` value and verify that files (log + state)
#          are created under that path, not the default location.
#
# 6. test_debug_log_contains_restart_entry
#        – After calling *restart_process*, wait for a DEBUG log message of the
#          form "restart_process called for pid=…" to appear.
#
# 7. test_server_stub_logs_warning
#        – Run `persistproc serve` and assert that a WARNING log record
#          indicating "Server functionality has not been implemented" is
#          emitted.
#
# Together, these tests constitute a *minimal* yet comprehensive end-to-end
# suite for a beta release: they cover process lifecycle, output retrieval,
# CLI I/O, logging, and configuration flags without relying on mocks.
