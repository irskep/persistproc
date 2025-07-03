from datetime import datetime, timezone, timedelta

from persistproc.core import ProcessManager, ProcessInfo


def _write_lines(path, base_ts):
    with path.open("w") as f:
        for i in range(6):
            ts = (base_ts + timedelta(seconds=i)).replace(tzinfo=timezone.utc)
            f.write(f"{ts.isoformat()[:-6]}Z line {i}\n")


def test_get_process_output_lines_and_filters(temp_dir, no_monitor_thread):
    pm = ProcessManager(temp_dir)
    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    p_info = ProcessInfo(
        pid=333,
        command="echo x",
        start_time=base.isoformat()[:-6] + "Z",
        status="exited",
        log_prefix="333.echo_x",
    )
    pm.processes[333] = p_info
    paths = pm.log_manager.get_log_paths(p_info.log_prefix)
    _write_lines(paths["stdout"], base)

    # last N
    assert pm.get_process_output(333, "stdout", lines=3) == [
        f"{(base + timedelta(seconds=i)).isoformat()[:-6]}Z line {i}\n"
        for i in range(3, 6)
    ]

    # before filter
    before = (base + timedelta(seconds=3)).isoformat()[:-6] + "Z"
    assert pm.get_process_output(333, "stdout", before_time=before) == [
        f"{(base + timedelta(seconds=i)).isoformat()[:-6]}Z line {i}\n"
        for i in range(3)
    ]

    # since > before returns empty
    lines = pm.get_process_output(
        333,
        "stdout",
        since_time=(base + timedelta(seconds=10)).isoformat()[:-6] + "Z",
        before_time=before,
    )
    assert lines == []
