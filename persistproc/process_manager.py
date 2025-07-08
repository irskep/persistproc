from __future__ import annotations

import logging
import os
import re
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
    ShutdownResult,
    ListProcessesResult,
    ProcessControlResult,
    ProcessInfo,
    ProcessOutputResult,
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
        server_log_path: Path,
        monitor=True,
        registry: Registry | None = None,
        data_dir: Path | None = None,
    ) -> None:  # noqa: D401 – simple init
        self.data_dir = data_dir
        self._server_log_path = server_log_path

        registry = registry or Registry(
            storage=lambda: ProcessStorageManager(), log=lambda path: LogManager(path)
        )

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

    def shutdown_monitor(self) -> None:  # noqa: D401
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
                return StartProcessResult(
                    error=f"Process with label '{process_label}' already running with PID {ent.pid}."
                )

        if not working_directory.is_dir():
            return StartProcessResult(
                error=f"Working directory '{working_directory}' does not exist."
            )

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

    def list(
        self,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> ListProcessesResult:  # noqa: D401
        # Special case: pid=0 requests server information only
        if pid == 0:
            # Get the current server log file path
            log_path_str = str(self._server_log_path)

            server_info = ProcessInfo(
                pid=os.getpid(),
                command=["persistproc", "serve"],
                working_directory=str(self.data_dir),
                status="running",
                label="persistproc-server",
                start_time=None,
                end_time=None,
                log_stdout=None,
                log_stderr=None,
                log_combined=log_path_str,
            )
            return ListProcessesResult(processes=[server_info])

        process_snapshot = self._storage.get_processes_values_snapshot()
        filtered_snapshot = self._filter_processes(
            process_snapshot, pid, command_or_label, working_directory
        )
        res = [self._to_public_info(ent) for ent in filtered_snapshot]
        return ListProcessesResult(processes=res)

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
        exit_code = ent.proc.returncode if ent.proc else 0
        self._storage.update_process_in_place(
            pid_to_stop,
            status="terminated",
            exit_code=exit_code,
            exit_time=_get_iso_ts(),
            proc=None,
        )

        logger.debug("event=stopped pid=%s exit_code=%s", pid_to_stop, exit_code)
        return StopProcessResult(exit_code=exit_code)

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
        logger.debug("restart: finding process")
        process_snapshot = self._storage.get_processes_values_snapshot()
        pid_to_restart, error = self._lookup_process_in_snapshot(
            process_snapshot, pid, label, command_or_label, working_directory
        )
        logger.debug("restart: finished finding process")

        if error:
            return RestartProcessResult(error=error)

        if pid_to_restart is None:
            return RestartProcessResult(error="Process not found to restart.")

        logger.debug("restart: getting process info for pid=%d", pid_to_restart)
        original_entry = self._storage.get_process_snapshot(pid_to_restart)
        if original_entry is None:
            logger.debug("restart: process not found for pid=%d", pid_to_restart)
            return RestartProcessResult(
                error=f"Process with PID {pid_to_restart} not found."
            )
        logger.debug("restart: got process info for pid=%d", pid_to_restart)

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

        if start_res.error is not None:
            return RestartProcessResult(error=start_res.error)

        logger.debug(
            "event=restart pid_old=%s pid_new=%s", pid_to_restart, start_res.pid
        )

        return RestartProcessResult(pid=start_res.pid)

    def ctrl(
        self,
        action: str,
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
        force: bool = False,
        label: str | None = None,
    ) -> ProcessControlResult:
        """Unified process control method for start, stop, and restart operations."""
        logger.debug(
            "ctrl: action=%s, pid=%s, command_or_label=%s, working_directory=%s",
            action,
            pid,
            command_or_label,
            working_directory,
        )

        # Validate action
        if action not in ["start", "stop", "restart"]:
            return ProcessControlResult(
                action=action,
                error=f"Invalid action '{action}'. Must be 'start', 'stop', or 'restart'.",
            )

        # Validate arguments based on action
        if action == "start":
            if command_or_label is None:
                return ProcessControlResult(
                    action=action,
                    error="command_or_label is required for start action",
                )
            if working_directory is None:
                return ProcessControlResult(
                    action=action,
                    error="working_directory is required for start action",
                )
            # For start, command_or_label is actually the command to run
            start_res = self.start(
                command=command_or_label,
                working_directory=Path(working_directory),
                environment=environment,
                label=label,
            )
            if start_res.error:
                return ProcessControlResult(action=action, error=start_res.error)

            return ProcessControlResult(
                action=action,
                pid=start_res.pid,
                log_stdout=start_res.log_stdout,
                log_stderr=start_res.log_stderr,
                log_combined=start_res.log_combined,
                label=start_res.label,
            )

        elif action == "stop":
            stop_res = self.stop(
                pid=pid,
                command_or_label=command_or_label,
                working_directory=Path(working_directory)
                if working_directory
                else None,
                force=force,
                label=label,
            )
            if stop_res.error:
                return ProcessControlResult(action=action, error=stop_res.error)

            # Get log paths for the stopped process if we have a PID
            target_pid = pid
            if target_pid is None and command_or_label is not None:
                # Find the PID that was stopped
                process_snapshot = self._storage.get_processes_values_snapshot()
                target_pid, _ = self._lookup_process_in_snapshot(
                    process_snapshot,
                    pid,
                    label,
                    command_or_label,
                    Path(working_directory) if working_directory else None,
                )

            log_stdout = None
            log_stderr = None
            log_combined = None
            process_label = None

            if target_pid is not None:
                ent = self._storage.get_process_snapshot(target_pid)
                if ent is not None and self._log_mgr is not None and ent.log_prefix:
                    paths = self._log_mgr.paths_for(ent.log_prefix)
                    log_stdout = str(paths.stdout)
                    log_stderr = str(paths.stderr)
                    log_combined = str(paths.combined)
                    process_label = ent.label

            return ProcessControlResult(
                action=action,
                pid=target_pid,
                exit_code=stop_res.exit_code,
                log_stdout=log_stdout,
                log_stderr=log_stderr,
                log_combined=log_combined,
                label=process_label,
            )

        elif action == "restart":
            # First find the process to get its exit code
            process_snapshot = self._storage.get_processes_values_snapshot()
            pid_to_restart, error = self._lookup_process_in_snapshot(
                process_snapshot,
                pid,
                label,
                command_or_label,
                Path(working_directory) if working_directory else None,
            )

            exit_code = None
            if pid_to_restart is not None:
                original_entry = self._storage.get_process_snapshot(pid_to_restart)
                if original_entry is not None and hasattr(original_entry, "exit_code"):
                    exit_code = original_entry.exit_code

            restart_res = self.restart(
                pid=pid,
                command_or_label=command_or_label,
                working_directory=Path(working_directory)
                if working_directory
                else None,
                label=label,
            )
            if restart_res.error:
                return ProcessControlResult(action=action, error=restart_res.error)

            # Get log paths for the new process
            log_stdout = None
            log_stderr = None
            log_combined = None
            process_label = None

            if restart_res.pid is not None:
                ent = self._storage.get_process_snapshot(restart_res.pid)
                if ent is not None and self._log_mgr is not None and ent.log_prefix:
                    paths = self._log_mgr.paths_for(ent.log_prefix)
                    log_stdout = str(paths.stdout)
                    log_stderr = str(paths.stderr)
                    log_combined = str(paths.combined)
                    process_label = ent.label

            return ProcessControlResult(
                action=action,
                pid=restart_res.pid,
                exit_code=exit_code,
                log_stdout=log_stdout,
                log_stderr=log_stderr,
                log_combined=log_combined,
                label=process_label,
            )

        # Should never reach here due to validation above
        return ProcessControlResult(
            action=action,
            error=f"Unhandled action '{action}'",
        )

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
        logger.debug("get_output: finding process")
        process_snapshot = self._storage.get_processes_values_snapshot()
        target_pid, error = self._lookup_process_in_snapshot(
            process_snapshot, pid, None, command_or_label, working_directory
        )
        logger.debug("get_output: finished finding process")

        if error:
            return ProcessOutputResult(error=error)

        if target_pid is None:
            return ProcessOutputResult(error="Process not found")

        logger.debug("get_output: getting process info for pid=%d", target_pid)
        ent = self._storage.get_process_snapshot(target_pid)
        if ent is None:
            logger.debug("get_output: process not found for pid=%d", target_pid)
            return ProcessOutputResult(error=f"PID {target_pid} not found")
        logger.debug("get_output: got process info for pid=%d", target_pid)

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

        with path.open("r", encoding="utf-8") as fh:
            all_lines = fh.readlines()

        # Optional ISO filtering (copied from previous implementation)
        def _parse_iso(ts: str) -> datetime:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(ts)
                # Handle naive datetime by assuming UTC timezone
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                # If parsing fails, try to parse as naive datetime and assume UTC
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", ""))
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError as e:
                    raise ValueError(f"Unable to parse timestamp: {ts}") from e

        # Start with all lines, then apply filters
        filtered_lines = all_lines

        try:
            if since_time:
                since_dt = _parse_iso(since_time)
                filtered_lines = [
                    ln
                    for ln in filtered_lines
                    if _parse_iso(ln.split(" ", 1)[0]) >= since_dt
                ]
            if before_time:
                before_dt = _parse_iso(before_time)
                filtered_lines = [
                    ln
                    for ln in filtered_lines
                    if _parse_iso(ln.split(" ", 1)[0]) < before_dt
                ]
        except (ValueError, IndexError) as e:
            # If timestamp parsing fails, fall back to returning all lines
            logger.warning(
                "Failed to parse timestamps in log filtering: %s, returning all lines",
                e,
            )
            filtered_lines = all_lines

        if lines is not None:
            filtered_lines = filtered_lines[-lines:]

        if filtered_lines:
            try:
                first_line_ts = _parse_iso(filtered_lines[0].split(" ", 1)[0])
                last_line_ts = _parse_iso(filtered_lines[-1].split(" ", 1)[0])

                lines_after = 0
                lines_before = 0

                for ln in all_lines:
                    try:
                        line_ts = _parse_iso(ln.split(" ", 1)[0])
                        if line_ts >= first_line_ts:
                            lines_after += 1
                        if line_ts <= last_line_ts:
                            lines_before += 1
                    except (ValueError, IndexError):
                        # Skip lines that can't be parsed
                        continue

                return ProcessOutputResult(
                    output=filtered_lines,
                    lines_before=lines_before,
                    lines_after=lines_after,
                )
            except (ValueError, IndexError):
                # If we can't parse timestamps, just return the filtered lines
                return ProcessOutputResult(
                    output=filtered_lines,
                    lines_before=0,
                    lines_after=0,
                )
        else:
            return ProcessOutputResult(output=[], lines_before=0, lines_after=0)

    def shutdown(self) -> ShutdownResult:  # noqa: D401
        """Shutdown all managed processes and then shutdown the server process."""
        server_pid = os.getpid()
        logger.info("event=shutdown_start server_pid=%s", server_pid)

        # Get a snapshot of all processes to kill
        processes_to_kill = self._storage.get_processes_values_snapshot()

        if not processes_to_kill:
            logger.debug("event=shutdown_no_processes")
        else:
            logger.debug(
                "event=shutdown_killing_processes count=%s",
                len(processes_to_kill),
            )

        unkilled_processes: list[tuple[int, str]] = []

        # Kill each process
        for ent in processes_to_kill:
            if ent.status == "running":
                logger.debug(
                    "event=shutdown_stopping pid=%s command=%s",
                    ent.pid,
                    " ".join(ent.command),
                )
                try:
                    result = self.stop(ent.pid, force=True)
                    if result.error is not None:
                        unkilled_processes.append((ent.pid, result.error))
                    logger.debug("event=shutdown_stopped pid=%s", ent.pid)
                except Exception as e:
                    logger.warning("event=shutdown_failed pid=%s error=%s", ent.pid, e)
            else:
                logger.debug(
                    "event=shutdown_skip pid=%s status=%s", ent.pid, ent.status
                )

        logger.info("event=shutdown_complete server_pid=%s", server_pid)

        if unkilled_processes:
            logger.warning(
                "event=shutdown_failed_to_kill_processes count=%s",
                len(unkilled_processes),
            )
            for pid, error in unkilled_processes:
                logger.warning(
                    "event=shutdown_failed_to_kill pid=%s error=%s", pid, error
                )

        # Schedule server termination after a brief delay to allow response to be sent
        def _kill_server():
            time.sleep(0.1)  # Brief delay to allow response to be sent
            logger.info("event=shutdown_terminating_server pid=%s", server_pid)
            os.kill(server_pid, signal.SIGTERM)

        threading.Thread(target=_kill_server, daemon=True).start()

        return ShutdownResult(
            pid=server_pid,
            error="\n".join([f"{pid}: {error}" for pid, error in unkilled_processes]),
        )

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

    def _filter_processes(
        self,
        process_snapshot: list[_ProcEntry],
        pid: int | None = None,
        command_or_label: str | None = None,
        working_directory: str | None = None,
    ) -> list[_ProcEntry]:
        """Filter process entries based on the provided criteria."""
        # If no filters provided, return all
        if pid is None and command_or_label is None and working_directory is None:
            return process_snapshot

        filtered_snapshot = []
        for ent in process_snapshot:
            # Check PID filter
            if pid is not None and ent.pid != pid:
                continue

            # Check command_or_label filter (check both label and command)
            if command_or_label is not None:
                # First try matching by label
                if ent.label == command_or_label:
                    pass  # matches
                else:
                    # Try matching by command
                    try:
                        if ent.command != shlex.split(command_or_label):
                            continue
                    except ValueError:
                        continue  # Skip if command parsing fails

            # Check working directory filter
            if (
                working_directory is not None
                and ent.working_directory != working_directory
            ):
                continue

            filtered_snapshot.append(ent)

        return filtered_snapshot

    def _to_public_info(self, ent: _ProcEntry) -> ProcessInfo:  # noqa: D401 – helper
        # Get log paths if log manager is available and we have a log prefix
        log_stdout = None
        log_stderr = None
        log_combined = None

        if self._log_mgr is not None and ent.log_prefix:
            paths = self._log_mgr.paths_for(ent.log_prefix)
            log_stdout = str(paths.stdout)
            log_stderr = str(paths.stderr)
            log_combined = str(paths.combined)

        return ProcessInfo(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory,
            status=ent.status,
            label=ent.label,
            start_time=ent.start_time,
            end_time=ent.exit_time,
            log_stdout=log_stdout,
            log_stderr=log_stderr,
            log_combined=log_combined,
        )

    def _monitor_loop(self) -> None:  # noqa: D401 – thread target
        """Background thread that monitors running processes and updates their status.

        Polls all running processes at regular intervals to detect when they exit,
        updating their status from 'running' to 'exited' and recording exit codes.
        Runs until the stop event is set via shutdown().
        """
        logger.debug("Monitor thread starting")

        while not self._storage.stop_event_is_set():
            procs_to_check = self._storage.get_processes_values_snapshot()
            logger.debug("event=monitor_tick_start num_procs=%d", len(procs_to_check))

            for ent in procs_to_check:
                if ent.status != "running" or ent.proc is None:
                    continue  # Skip non-running processes

                if ent.proc.poll() is not None:
                    # Process has exited - update via storage manager
                    self._storage.update_process_in_place(
                        ent.pid,
                        status="exited",
                        exit_code=ent.proc.returncode,
                        exit_time=_get_iso_ts(),
                    )
                    logger.info(
                        "Process %s exited with code %s", ent.pid, ent.proc.returncode
                    )

            # Cleanup old terminated processes periodically
            self._storage.cleanup_old_terminated_processes(max_terminated=10)

            logger.debug(
                "event=monitor_tick_end, checked %d procs", len(procs_to_check)
            )
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
