"""Fake implementations for testing persistproc components without real dependencies."""

from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from persistproc.process_storage_manager import _ProcEntry
from persistproc.process_manager import Registry


class FakeProcessStorageManager:
    """Fake ProcessStorageManager for unit testing - no threading needed."""

    def __init__(self):
        self._processes: dict[int, _ProcEntry] = {}
        self._stop_evt = threading.Event()

    def add_process(self, entry: _ProcEntry) -> None:
        """Add a process entry to storage."""
        self._processes[entry.pid] = entry

    def get_process_snapshot(self, pid: int) -> _ProcEntry | None:
        """Get a process entry by PID. Returns None if not found."""
        return self._processes.get(pid)

    def get_processes_values_snapshot(self) -> list[_ProcEntry]:
        """Get a snapshot of all process entries."""
        return list(self._processes.values())

    def get_processes_dict_snapshot(self) -> dict[int, _ProcEntry]:
        """Get a snapshot of the entire processes dict."""
        return dict(self._processes)

    def update_process_in_place(
        self,
        pid: int,
        status: str | None = None,
        exit_code: int | None = None,
        exit_time: str | None = None,
        proc=None,
    ) -> None:
        """Update process fields in place."""
        if pid in self._processes:
            entry = self._processes[pid]
            if status is not None:
                entry.status = status
            if exit_code is not None:
                entry.exit_code = exit_code
            if exit_time is not None:
                entry.exit_time = exit_time
            if proc is not None:
                entry.proc = proc

    def stop_event_set(self) -> None:
        """Signal the stop event."""
        self._stop_evt.set()

    def stop_event_is_set(self) -> bool:
        """Check if stop event is set."""
        return self._stop_evt.is_set()

    def cleanup_old_terminated_processes(self, max_terminated: int = 10) -> None:
        """Remove oldest terminated processes, keeping only max_terminated."""
        # Find all terminated processes
        terminated_entries = [
            (pid, entry)
            for pid, entry in self._processes.items()
            if entry.status in ("exited", "terminated", "failed")
        ]

        # If we have more than max_terminated, remove the oldest
        if len(terminated_entries) > max_terminated:
            # Sort by exit_time, oldest first (None exit_time goes first)
            terminated_entries.sort(key=lambda x: x[1].exit_time or "")

            # Remove oldest until we're at the limit
            to_remove = len(terminated_entries) - max_terminated
            for i in range(to_remove):
                pid_to_remove = terminated_entries[i][0]
                del self._processes[pid_to_remove]


@dataclass
class FakeLogPaths:
    """Fake log paths for testing."""

    stdout: Path
    stderr: Path
    combined: Path

    def __getitem__(self, item: str) -> Path:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


class FakeLogManager:
    """Fake LogManager for unit testing."""

    def __init__(self, base_dir: Path):
        self._dir = base_dir
        self._started_pumps: list[tuple[Any, str]] = []

    def paths_for(self, prefix: str) -> FakeLogPaths:
        """Return fake log paths."""
        return FakeLogPaths(
            stdout=self._dir / f"{prefix}.stdout",
            stderr=self._dir / f"{prefix}.stderr",
            combined=self._dir / f"{prefix}.combined",
        )

    def start_pumps(self, proc: Any, prefix: str) -> None:
        """Record that pumps were started (fake implementation)."""
        self._started_pumps.append((proc, prefix))

    def get_started_pumps(self) -> list[tuple[Any, str]]:
        """Return list of started pumps for testing."""
        return self._started_pumps.copy()


@dataclass
class FakeSubprocessPopen:
    """Fake subprocess.Popen for testing - avoids real subprocess usage."""

    pid: int
    returncode: int | None = None
    stdout: Any = None
    stderr: Any = None
    _poll_count: int = field(default=0, init=False)

    def poll(self) -> int | None:
        """Simulate polling the process."""
        self._poll_count += 1
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        """Simulate waiting for process."""
        if self.returncode is None:
            if timeout is not None and timeout <= 0:
                # Simulate timeout without importing subprocess
                class FakeTimeoutExpired(Exception):
                    def __init__(self, cmd, timeout):
                        self.cmd = cmd
                        self.timeout = timeout

                raise FakeTimeoutExpired(cmd=["fake"], timeout=timeout)
            # For testing, assume process exits immediately
            self.returncode = 0
        return self.returncode

    def send_signal(self, sig: int) -> None:
        """Simulate sending signal."""
        pass

    def terminate(self) -> None:
        """Simulate terminating process."""
        if self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        """Simulate killing process."""
        if self.returncode is None:
            self.returncode = -9


def create_fake_registry(base_dir: Path) -> Any:
    """Create a fake registry for testing ProcessManager."""
    storage = FakeProcessStorageManager()

    return Registry(storage=lambda: storage, log=lambda path: FakeLogManager(path))


def create_fake_proc_entry(
    pid: int = 1234,
    command: list[str] | None = None,
    working_directory: str | None = None,
    status: str = "running",
    label: str = "test-process",
    proc: Any = None,
    log_prefix: str | None = None,
) -> _ProcEntry:
    """Create a fake process entry for testing."""
    if command is None:
        command = ["echo", "hello"]

    if working_directory is None:
        working_directory = tempfile.gettempdir()

    if log_prefix is None:
        log_prefix = f"{pid}.echo"

    return _ProcEntry(
        pid=pid,
        command=command,
        working_directory=working_directory,
        environment={},
        start_time="2024-01-01T00:00:00.000Z",
        status=status,
        log_prefix=log_prefix,
        label=label,
        proc=proc,
    )
