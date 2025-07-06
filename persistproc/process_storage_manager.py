from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass, field

from persistproc.process_types import ProcessInfo

logger = logging.getLogger(__name__)


@dataclass
class _ProcEntry:  # noqa: D401 – internal state
    pid: int
    command: list[str]
    working_directory: str
    environment: dict[str, str] | None
    start_time: str
    status: str  # running | exited | terminated | failed
    log_prefix: str
    label: str
    exit_code: int | None = None
    exit_time: str | None = None
    # Keep a reference so we can signal/poll. Excluded from comparisons.
    proc: subprocess.Popen | None = field(repr=False, compare=False, default=None)


class ProcessStorageManager:
    """Manages thread-safe access to the process storage dict."""

    def __init__(self):
        self._processes: dict[int, _ProcEntry] = {}
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()

    def add_process(self, entry: _ProcEntry) -> None:
        """Add a process entry to storage."""
        with self._lock:
            self._processes[entry.pid] = entry

    def get_process_snapshot(self, pid: int) -> _ProcEntry | None:
        """Get a process entry by PID. Returns None if not found."""
        with self._lock:
            return self._processes.get(pid)

    def get_processes_values_snapshot(self) -> list[_ProcEntry]:
        """Get a snapshot of all process entries (equivalent to _processes.values())."""
        with self._lock:
            return list(self._processes.values())

    def get_processes_dict_snapshot(self) -> dict[int, _ProcEntry]:
        """Get a snapshot of the entire processes dict."""
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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

    def _to_public_info(self, ent: _ProcEntry) -> ProcessInfo:
        """Convert internal entry to public info."""
        return ProcessInfo(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory,
            status=ent.status,
            label=ent.label,
            start_time=ent.start_time,
            end_time=ent.exit_time,
        )
