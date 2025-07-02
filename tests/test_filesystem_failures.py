import errno
from pathlib import Path

import pytest

from persistproc.core import ProcessManager


@pytest.fixture
def pm_no_monitor(temp_dir, no_monitor_thread):
    """Provide a ProcessManager instance without its monitor thread."""
    return ProcessManager(temp_dir)


# ---------------------------------------------------------------------------
# File-system failure simulations
# ---------------------------------------------------------------------------


def _raise_enospc(*_args, **_kwargs):
    """Helper that mimics a disk-full OSError."""
    raise OSError(errno.ENOSPC, "No space left on device")


def test_start_process_disk_full(pm_no_monitor, monkeypatch):
    """start_process should propagate errors if log files cannot be opened due
    to disk-full conditions (ENOSPC)."""

    # Patch Path.open used inside LogManager.start_logging to raise ENOSPC
    monkeypatch.setattr(Path, "open", _raise_enospc, raising=True)

    with pytest.raises(OSError) as exc:
        pm_no_monitor.start_process("echo hello")

    assert exc.value.errno == errno.ENOSPC
