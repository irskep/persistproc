from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from persistproc.core import ProcessManager, ProcessInfo


@pytest.fixture
def pm_no_monitor(temp_dir, no_monitor_thread):
    """Provide a ProcessManager instance without its monitor thread."""
    return ProcessManager(temp_dir)


# ---------------------------------------------------------------------------
# get_process_output timestamp filtering
# ---------------------------------------------------------------------------


def _write_log_lines(log_path: Path, base_ts: datetime):
    """Helper to create dummy log file with 5 timestamped lines."""
    with log_path.open("w") as f:
        for i in range(5):
            ts = (base_ts + timedelta(seconds=i)).replace(tzinfo=timezone.utc)
            f.write(f"{ts.isoformat()[:-6]}Z line {i}\n")


@pytest.mark.parametrize(
    "since_delta, before_delta, expected_count",
    [
        (None, None, 5),  # All lines
        (1, None, 4),  # Since t+1 => 4 lines
        (None, 4, 4),  # Before t+4 => lines 0-3
        (1, 4, 3),  # Between => lines 1-3
    ],
)
def test_get_process_output_filters(
    pm_no_monitor, since_delta, before_delta, expected_count
):
    base_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Register a fake exited process
    p_info = ProcessInfo(
        pid=42,
        command="echo x",
        start_time=base_ts.isoformat()[:-6] + "Z",
        status="exited",
        log_prefix="42.echo_x",
    )
    pm_no_monitor.processes[42] = p_info

    log_paths = pm_no_monitor.log_manager.get_log_paths(p_info.log_prefix)
    _write_log_lines(log_paths["stdout"], base_ts)

    kwargs = {}
    if since_delta is not None:
        kwargs["since_time"] = (base_ts + timedelta(seconds=since_delta)).isoformat()[
            :-6
        ] + "Z"
    if before_delta is not None:
        kwargs["before_time"] = (base_ts + timedelta(seconds=before_delta)).isoformat()[
            :-6
        ] + "Z"

    lines = pm_no_monitor.get_process_output(42, "stdout", **kwargs)
    assert len(lines) == expected_count


# ---------------------------------------------------------------------------
# Additional filter edge-cases
# ---------------------------------------------------------------------------


def test_get_process_output_since_after_before(pm_no_monitor, tmp_path):
    """since_time newer than before_time should return empty list, not raise."""

    base_ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    p_info = ProcessInfo(
        pid=55,
        command="echo x",
        start_time=base_ts.isoformat()[:-6] + "Z",
        status="exited",
        log_prefix="55.echo_x",
    )
    pm_no_monitor.processes[55] = p_info
    log_paths = pm_no_monitor.log_manager.get_log_paths(p_info.log_prefix)
    _write_log_lines(log_paths["stdout"], base_ts)

    lines = pm_no_monitor.get_process_output(
        55,
        "stdout",
        since_time=(base_ts + timedelta(seconds=10)).isoformat()[:-6] + "Z",
        before_time=(base_ts + timedelta(seconds=5)).isoformat()[:-6] + "Z",
    )
    assert lines == []


@pytest.mark.parametrize("bad_ts", ["not-a-date", "2025-13-40T00:00:00Z"])
def test_get_process_output_invalid_timestamp(pm_no_monitor, bad_ts):
    base_ts = datetime.now(timezone.utc)
    p_info = ProcessInfo(
        pid=56,
        command="echo x",
        start_time=base_ts.isoformat()[:-6] + "Z",
        status="exited",
        log_prefix="56.echo_x",
    )
    pm_no_monitor.processes[56] = p_info
    log_paths = pm_no_monitor.log_manager.get_log_paths(p_info.log_prefix)
    _write_log_lines(log_paths["stdout"], base_ts)

    with pytest.raises(ValueError):
        pm_no_monitor.get_process_output(56, "stdout", since_time=bad_ts)
