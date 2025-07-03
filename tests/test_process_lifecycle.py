import sys
import time
from pathlib import Path
import os
import shutil

import pytest

from persistproc import process_manager as _pm_mod
from persistproc.process_manager import ProcessManager
from persistproc.logging_utils import setup_logging


def test_start_and_stop_process_roundtrip():
    """End-to-end test: start a long-running process, verify it is running, then stop it.

    The test avoids arbitrary sleeps by relying on ProcessManager's synchronous
    APIs. A 60-second upper bound is implicitly provided by the default
    *stop_process* timeouts inside *ProcessManager* (≤10 s) plus pytest's own
    default test timeout, so we do not add additional waits here.
    """

    # ---------------------------------------------------------------------
    # Bootstrap a fresh ProcessManager instance pointing at the tmp_path.
    # ---------------------------------------------------------------------
    artifacts_root = Path(__file__).parent / "_artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    data_dir = artifacts_root / "process_lifecycle"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir()

    setup_logging(2, data_dir)  # DEBUG verbosity for rich logs
    _pm_mod._POLL_INTERVAL = 0.05
    pm = ProcessManager()
    pm.bootstrap(data_dir)

    # ---------------------------------------------------------------------
    # Run the lightweight *counter.py* helper so the entire lifecycle finishes
    # in well under 5 seconds.  The script prints one line then exits 0.
    # ---------------------------------------------------------------------
    cmd = f"{sys.executable} -u -c \"print('hello')\""

    start_res = pm.start_process(cmd)
    pid = start_res.pid

    # ---------------------------------------------------------------------
    # Confirm the process appears as *running* immediately after start.
    # ---------------------------------------------------------------------
    list_res = pm.list_processes()
    assert any(p.pid == pid and p.status == "running" for p in list_res.processes)

    # Wait briefly for the process to produce output and exit naturally.
    time.sleep(0.1)

    # Use the public API to ensure the process is fully reaped. This should
    # return immediately because the process has already exited.
    stop_res = pm.stop_process(pid)
    assert stop_res.exit_code == 0

    # Ensure the monitor thread is cleanly shut down to avoid leaks between
    # tests.
    pm.shutdown()
