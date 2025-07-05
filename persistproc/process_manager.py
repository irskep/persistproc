from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import threading
import time
import traceback
from collections.abc import Callable

# Comprehensive ProcessManager implementation.
# Standard library imports
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from persistproc.log_manager import LogManager
from persistproc.process_storage_manager import ProcessStorageManager, _ProcEntry
from persistproc.process_types import (
    ListProcessesResult,
    ProcessInfo,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    RestartProcessResult,
    StartProcessResult,
    StopProcessResult,
)

__all__ = ["ProcessManager"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Small utilities (duplicated from *before_rewrite.utils* to avoid dependency)
# ---------------------------------------------------------------------------


def _get_iso_ts() -> str:  # noqa: D401 – helper
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _escape_cmd(cmd: str, max_len: int = 50) -> str:  # noqa: D401 – helper
    """Return *cmd* sanitised for use in filenames."""
    import re

    cmd = re.sub(r"\s+", "_", cmd)
    cmd = re.sub(r"[^a-zA-Z0-9_-]", "", cmd)
    return cmd[:max_len]


def get_label(explicit_label: str | None, command: str, working_directory) -> str:
    """Generate a process label from explicit label or command + working directory."""
    if explicit_label:
        return explicit_label

    return f"{command} in {working_directory}"


# Interval for the monitor thread (overridable for tests)
_POLL_INTERVAL = float(os.environ.get("PERSISTPROC_TEST_POLL_INTERVAL", "1.0"))


@dataclass
class Registry:
    """
    Contains factory functions for dependencies, so swapping in fakes in tests is easy
    """

    storage: Callable[[], ProcessStorageManager]
    log: Callable[[str], LogManager]


class ProcessManager:  # noqa: D101
    def __init__(
        self,
        monitor=True,
        registry: Registry | None = None,
        data_dir: Path | None = None,
        server_log_path: Path | None = None,
    ) -> None:  # noqa: D401 – simple init
        self.data_dir = data_dir

        self._storage = registry.storage()
        self._log_mgr = registry.log(data_dir / "process_logs")

        # monitor thread is started on first *bootstrap*
        self.monitor = monitor
        self._monitor_thread: threading.Thread | None = None

        if self._monitor_thread is None and self.monitor:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True
            )
            self._monitor_thread.start()

        logger.debug("ProcessManager bootstrapped dir=%s", data_dir)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def shutdown(self) -> None:  # noqa: D401
        """Signal the monitor thread to exit (used by tests)."""
        self._storage.stop_event_set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Core API – exposed via CLI & MCP tools
    # ------------------------------------------------------------------

    # NOTE: The docstrings are intentionally minimal – rich help is provided
    #       in *tools.py* and the CLI.

    def start(
        self,
        command: str,
        working_directory: Path,
        environment: dict[str, str] | None = None,
        label: str | None = None,
    ) -> StartProcessResult:  # noqa: D401
        if self._log_mgr is None:
            raise RuntimeError("ProcessManager.bootstrap() must be called first")

        logger.debug("start: received command=%s type=%s", command, type(command))

        # Generate label before duplicate check
        process_label = get_label(label, command, str(working_directory))

        # Prevent duplicate *running* labels (helps humans)
        process_snapshot = self._storage.get_processes_values_snapshot()
        for ent in process_snapshot:
            # Check for duplicate labels in running processes
            if ent.label == process_label and ent.status == "running":
                raise ValueError(
                    f"Process with label '{process_label}' already running with PID {ent.pid}."
                )

        if not working_directory.is_dir():
            raise ValueError(f"Working directory '{working_directory}' does not exist.")

        diagnostic_info_for_errors = {
            "command": command,
            "working_directory": str(working_directory),
        }

        try:
            proc = subprocess.Popen(  # noqa: S603 – user command
                shlex.split(command),
                cwd=str(working_directory),
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                # Put the child in a different process group so a SIGINT will
                # kill only the child, not the whole process group.
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except FileNotFoundError as exc:
            return StartProcessResult(
                error=f"Command not found: {exc.filename}\n\n{diagnostic_info_for_errors}"
            )
        except PermissionError as exc:
            return StartProcessResult(
                error=f"Permission denied: {exc.filename}\n\n{diagnostic_info_for_errors}"
            )
        except Exception as exc:  # pragma: no cover – safety net
            return StartProcessResult(
                error=f"Failed to start process: {exc}\n\n{traceback.format_exc()}"
            )

        prefix = f"{proc.pid}.{_escape_cmd(command)}"
        self._log_mgr.start_pumps(proc, prefix)

        ent = _ProcEntry(
            pid=proc.pid,
            command=shlex.split(command),
            working_directory=str(working_directory),
            environment=environment,
            start_time=_get_iso_ts(),
            status="running",
            log_prefix=prefix,
            label=process_label,
            proc=proc,
        )

        self._storage.add_process(ent)

        logger.info("Process %s started", proc.pid)
        logger.debug(
            "event=start pid=%s cmd=%s cwd=%s log_prefix=%s",
            proc.pid,
            shlex.join(ent.command),
            ent.working_directory,
            prefix,
        )
        return StartProcessResult(
            pid=proc.pid,
            log_stdout=self._log_mgr.paths_for(prefix).stdout,
            log_stderr=self._log_mgr.paths_for(prefix).stderr,
            log_combined=self._log_mgr.paths_for(prefix).combined,
            label=process_label,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list(self) -> ListProcessesResult:  # noqa: D401
        process_snapshot = self._storage.get_processes_values_snapshot()
        res = [self._to_public_info(ent) for ent in process_snapshot]
        return ListProcessesResult(processes=res)

    def get_status(
        self,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
    ) -> ProcessStatusResult:  # noqa: D401
        process_snapshot = self._storage.get_processes_values_snapshot()
        target_pid, error = self._lookup_process_in_snapshot(
            process_snapshot, pid, None, command_or_label, working_directory
        )

        if error:
            return ProcessStatusResult(error=error)

        if target_pid is None:
            return ProcessStatusResult(error="Process not found")

        ent = self._storage.get_process_snapshot(target_pid)
        if ent is None:
            return ProcessStatusResult(error=f"PID {target_pid} not found")

        return ProcessStatusResult(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory,
            status=ent.status,
            label=ent.label,
        )

    # ------------------------------------------------------------------
    # Control helpers
    # ------------------------------------------------------------------

    def stop(
        self,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
        force: bool = False,
        label: str | None = None,
    ) -> StopProcessResult:  # noqa: D401
        if pid is None and command_or_label is None and label is None:
            return StopProcessResult(
                error="Either pid, command_or_label, or label must be provided to stop"
            )

        # Use _lookup_process_in_snapshot to find the process
        process_snapshot = self._storage.get_processes_values_snapshot()
        pid_to_stop, error = self._lookup_process_in_snapshot(
            process_snapshot, pid, label, command_or_label, working_directory
        )

        if error:
            return StopProcessResult(error=error)

        if pid_to_stop is None:
            return StopProcessResult(error="Process not found")

        ent = self._storage.get_process_snapshot(pid_to_stop)
        if ent is None:
            return StopProcessResult(error=f"PID {pid_to_stop} not found")

        if ent.status != "running":
            return StopProcessResult(error=f"Process {pid_to_stop} is not running")

        # Send SIGTERM first for graceful shutdown
        try:
            self._send_signal(pid_to_stop, signal.SIGTERM)
            logger.debug("Sent SIGTERM to pid=%s", pid_to_stop)
        except ProcessLookupError:
            # Process already gone
            pass

        timeout = 8.0  # XXX TIMEOUT – graceful wait
        exited = self._wait_for_exit(ent.proc, timeout)
        if not exited and not force:
            # Escalate to SIGKILL once and wait briefly.
            try:
                self._send_signal(pid_to_stop, signal.SIGKILL)
                logger.warning("Escalated to SIGKILL pid=%s", pid_to_stop)
            except ProcessLookupError:
                pass  # Process vanished between checks.

            exited = self._wait_for_exit(ent.proc, 2.0)  # XXX TIMEOUT – short

        if not exited:
            logger.error("event=stop_timeout pid=%s", pid_to_stop)
            return StopProcessResult(error="timeout")

        # Process exited – record metadata.
        self._storage.update_process_in_place(
            pid_to_stop,
            status="terminated",
            exit_code=ent.exit_code if ent.exit_code is not None else 0,
            exit_time=_get_iso_ts(),
            proc=None,
        )

        logger.debug("event=stopped pid=%s exit_code=%s", pid_to_stop, ent.exit_code)
        return StopProcessResult(exit_code=ent.exit_code)

    def restart(
        self,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
        label: str | None = None,
    ) -> RestartProcessResult:  # noqa: D401
        """Attempt to stop then start *pid*.

        On success returns ``RestartProcessResult(pid=new_pid)`` for parity with
        :py:meth:`stop`.  If stopping timed-out the same
        ``RestartProcessResult`` with ``error='timeout'`` is propagated so callers
        can decide how to handle the failure.
        """
        logger.debug(
            "restart: pid=%s, command_or_label=%s, cwd=%s",
            pid,
            command_or_label,
            working_directory,
        )

        # Use _lookup_process to find the process
        logger.debug("restart: acquiring lock to find process")
        with self._lock:
            logger.debug("restart: lock acquired to find process")
            pid_to_restart, error = self._lookup_process(
                pid, label, command_or_label, working_directory
            )
        logger.debug("restart: lock released after finding process")

        if error:
            return RestartProcessResult(error=error)

        if pid_to_restart is None:
            return RestartProcessResult(error="Process not found to restart.")

        logger.debug("restart: acquiring lock for pid=%d", pid_to_restart)
        with self._lock:
            logger.debug("restart: lock acquired for pid=%d", pid_to_restart)
            try:
                original_entry = self._get_process_info_within_lock(pid_to_restart)
            except ValueError:
                logger.debug("restart: lock released for pid=%d", pid_to_restart)
                return RestartProcessResult(
                    error=f"Process with PID {pid_to_restart} not found."
                )
        logger.debug("restart: lock released for pid=%d", pid_to_restart)

        # Retain original parameters for restart
        original_command_list = original_entry.command
        logger.debug(
            "restart: original_command_list=%s type=%s",
            original_command_list,
            type(original_command_list),
        )
        original_command_str = shlex.join(original_command_list)
        logger.debug(
            "restart: original_command_str=%s type=%s",
            original_command_str,
            type(original_command_str),
        )
        cwd = (
            Path(original_entry.working_directory)
            if original_entry.working_directory
            else None
        )
        env = original_entry.environment

        stop_res = self.stop(pid_to_restart, force=False)
        if stop_res.error is not None:
            # Forward failure.
            return RestartProcessResult(error=stop_res.error)

        logger.debug(
            "restart: calling start with command=%s type=%s",
            original_command_str,
            type(original_command_str),
        )
        start_res = self.start(
            original_command_str,
            working_directory=cwd,
            environment=env,
            label=original_entry.label,
        )

        logger.debug(
            "event=restart pid_old=%s pid_new=%s", pid_to_restart, start_res.pid
        )

        return RestartProcessResult(pid=start_res.pid)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def get_output(
        self,
        pid: int | None = None,
        stream: str = "combined",
        lines: int | None = None,
        before_time: str | None = None,
        since_time: str | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
    ) -> ProcessOutputResult:  # noqa: D401
        logger.debug("get_output: acquiring lock")
        with self._lock:
            logger.debug("get_output: lock acquired")
            target_pid, error = self._lookup_process(
                pid, None, command_or_label, working_directory
            )
        logger.debug("get_output: lock released")

        if error:
            return ProcessOutputResult(error=error)

        if target_pid is None:
            return ProcessOutputResult(error="Process not found")

        logger.debug("get_output: acquiring lock for pid=%d", target_pid)
        with self._lock:
            logger.debug("get_output: lock acquired for pid=%d", target_pid)
            try:
                ent = self._get_process_info_within_lock(target_pid)
            except ValueError as e:
                logger.debug("get_output: lock released for pid=%d", target_pid)
                return ProcessOutputResult(error=str(e))
        logger.debug("get_output: lock released for pid=%d", target_pid)

        if self._log_mgr is None:
            raise RuntimeError("Log manager not available")

        if target_pid == 0:
            # Special case – read the main CLI/server log file if known.
            if self._server_log_path and self._server_log_path.exists():
                with self._server_log_path.open("r", encoding="utf-8") as fh:
                    all_lines = fh.readlines()
                return ProcessOutputResult(output=all_lines)
            return ProcessOutputResult(output=[])  # Unknown path – empty

        paths = self._log_mgr.paths_for(ent.log_prefix)
        if stream not in paths:
            return ProcessOutputResult(error="stream must be stdout|stderr|combined")
        path = paths[stream]
        if not path.exists():
            return ProcessOutputResult(output=[])

        filtered_lines: list[str] = []

        with path.open("r", encoding="utf-8") as fh:
            all_lines = fh.readlines()

        # Optional ISO filtering (copied from previous implementation)
        def _parse_iso(ts: str) -> datetime:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)

        if since_time:
            since_dt = _parse_iso(since_time)
            filtered_lines = [
                ln for ln in all_lines if _parse_iso(ln.split(" ", 1)[0]) >= since_dt
            ]
        if before_time:
            before_dt = _parse_iso(before_time)
            all_lines = [
                ln for ln in all_lines if _parse_iso(ln.split(" ", 1)[0]) < before_dt
            ]

        if lines is not None:
            filtered_lines = all_lines[-lines:]

        if filtered_lines:
            first_line_ts = _parse_iso(filtered_lines[0].split(" ", 1)[0])
            last_line_ts = _parse_iso(filtered_lines[-1].split(" ", 1)[0])
            lines_after = len(
                [
                    ln
                    for ln in all_lines
                    if _parse_iso(ln.split(" ", 1)[0]) >= first_line_ts
                ]
            )
            lines_before = len(
                [
                    ln
                    for ln in all_lines
                    if _parse_iso(ln.split(" ", 1)[0]) <= last_line_ts
                ]
            )

            return ProcessOutputResult(
                output=filtered_lines,
                lines_before=lines_before,
                lines_after=lines_after,
            )
        else:
            return ProcessOutputResult(output=[], lines_before=0, lines_after=0)

    def get_log_paths(
        self,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
    ) -> ProcessLogPathsResult:  # noqa: D401
        logger.debug("get_log_paths: acquiring lock")
        with self._lock:
            logger.debug("get_log_paths: lock acquired")
            target_pid, error = self._lookup_process(
                pid, None, command_or_label, working_directory
            )
        logger.debug("get_log_paths: lock released")

        if error:
            return ProcessLogPathsResult(error=error)

        if target_pid is None:
            return ProcessLogPathsResult(error="Process not found")

        logger.debug("get_log_paths: acquiring lock for pid=%d", target_pid)
        with self._lock:
            logger.debug("get_log_paths: lock acquired for pid=%d", target_pid)
            try:
                ent = self._get_process_info_within_lock(target_pid)
                logger.debug("get_log_paths: lock released for pid=%d", target_pid)
            except ValueError as e:
                logger.debug("get_log_paths: lock released for pid=%d", target_pid)
                return ProcessLogPathsResult(error=str(e))

        if self._log_mgr is None:
            raise RuntimeError("Log manager not available")

        paths = self._log_mgr.paths_for(ent.log_prefix)
        return ProcessLogPathsResult(stdout=str(paths.stdout), stderr=str(paths.stderr))

    def kill_persistproc(self) -> dict[str, int]:  # noqa: D401
        """Kill all managed processes and then kill the server process."""
        server_pid = os.getpid()
        logger.info("event=kill_persistproc_start server_pid=%s", server_pid)

        # Get a snapshot of all processes to kill
        with self._lock:
            processes_to_kill = list(self._processes.values())

        if not processes_to_kill:
            logger.debug("event=kill_persistproc_no_processes")
        else:
            logger.debug(
                "event=kill_persistproc_killing_processes count=%s",
                len(processes_to_kill),
            )

        # Kill each process
        for ent in processes_to_kill:
            if ent.status == "running":
                logger.debug(
                    "event=kill_persistproc_stopping pid=%s command=%s",
                    ent.pid,
                    " ".join(ent.command),
                )
                try:
                    self.stop(ent.pid, force=True)
                    logger.debug("event=kill_persistproc_stopped pid=%s", ent.pid)
                except Exception as e:
                    logger.warning(
                        "event=kill_persistproc_failed pid=%s error=%s", ent.pid, e
                    )
            else:
                logger.debug(
                    "event=kill_persistproc_skip pid=%s status=%s", ent.pid, ent.status
                )

        logger.info("event=kill_persistproc_complete server_pid=%s", server_pid)

        # Schedule server termination after a brief delay to allow response to be sent
        def _kill_server():
            time.sleep(0.1)  # Brief delay to allow response to be sent
            logger.info("event=kill_persistproc_terminating_server pid=%s", server_pid)
            os.kill(server_pid, signal.SIGTERM)

        threading.Thread(target=_kill_server, daemon=True).start()

        return {"pid": server_pid}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _lookup_process_in_snapshot(
        self,
        process_snapshot: list[_ProcEntry],
        pid: int | None = None,
        label: str | None = None,
        command_or_label: str | None = None,
        working_directory: Path | None = None,
    ) -> tuple[int | None, str | None]:
        # If pid is provided, use it directly
        if pid is not None:
            return pid, None

        # If explicit label is provided, use it
        if label is not None:
            for p in process_snapshot:
                if p.label == label and p.status == "running":
                    return p.pid, None
            return None, f"No running process found with label: {label}"

        # Handle command_or_label disambiguation
        if command_or_label is None:
            return None, "No pid, label, or command_or_label provided"

        # First try as label
        for p in process_snapshot:
            if p.label == command_or_label and p.status == "running":
                return p.pid, None

        # Then try as command
        try:
            candidates_by_command = [
                p
                for p in process_snapshot
                if p.command == shlex.split(command_or_label) and p.status == "running"
            ]
        except ValueError as e:
            return None, f"Error parsing command: {e}"

        if working_directory is not None:
            candidates_by_command = [
                p
                for p in candidates_by_command
                if p.working_directory == str(working_directory)
            ]

        if len(candidates_by_command) == 1:
            return candidates_by_command[0].pid, None
        elif len(candidates_by_command) > 1:
            return None, f"Multiple processes found for '{command_or_label}'"
        else:
            return None, f"No process found for '{command_or_label}'"

    def _get_process_info_within_lock(self, pid: int) -> _ProcEntry:  # noqa: D401 – helper (assumes lock held)
        if pid not in self._processes:
            raise ValueError(f"PID {pid} not found")
        return self._processes[pid]

    def _to_public_info(self, ent: _ProcEntry) -> ProcessInfo:  # noqa: D401 – helper
        return ProcessInfo(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory,
            status=ent.status,
            label=ent.label,
        )

    def _monitor_loop(self) -> None:  # noqa: D401 – thread target
        """Background thread that monitors running processes and updates their status.

        Polls all running processes at regular intervals to detect when they exit,
        updating their status from 'running' to 'exited' and recording exit codes.
        Runs until the stop event is set via shutdown().
        """
        logger.debug("Monitor thread starting")

        while not self._stop_evt.is_set():
            logger.debug("event=monitor_tick_start num_procs=%d", len(self._processes))

            logger.debug("monitor_loop: acquiring lock")
            with self._lock:
                logger.debug("monitor_loop: lock acquired")
                procs_to_check = list(self._processes.values())

                for ent in procs_to_check:
                    if ent.status != "running" or ent.proc is None:
                        continue  # Skip non-running processes

                    if ent.proc.poll() is not None:
                        # Process has exited.
                        ent.status = "exited"
                        ent.exit_code = ent.proc.returncode
                        ent.exit_time = _get_iso_ts()
                        logger.info(
                            "Process %s exited with code %s", ent.pid, ent.exit_code
                        )
                logger.debug(
                    "monitor_loop: lock released, checked %d procs",
                    len(procs_to_check),
                )

            logger.debug("event=monitor_tick_end")
            time.sleep(_POLL_INTERVAL)

        logger.debug("Monitor thread exiting")

    # ------------------ signal helpers ------------------

    @staticmethod
    def _send_signal(pid: int, sig: signal.Signals) -> None:  # noqa: D401
        os.killpg(os.getpgid(pid), sig)  # type: ignore[arg-type]

    @staticmethod
    def _wait_for_exit(proc: subprocess.Popen | None, timeout: float) -> bool:  # noqa: D401
        if proc is None:
            return True
        logger.debug(
            "event=wait_for_exit pid=%s timeout=%s", getattr(proc, "pid", None), timeout
        )
        try:
            proc.wait(timeout=timeout)
            logger.debug(
                "event=wait_for_exit_done pid=%s exited=True",
                getattr(proc, "pid", None),
            )
            return True
        except subprocess.TimeoutExpired:
            logger.debug(
                "event=wait_for_exit_done pid=%s exited=False",
                getattr(proc, "pid", None),
            )
            return False


__ALL__ = ["ProcessManager"]
__ALL__ = ["ProcessManager"]
