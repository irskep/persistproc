from __future__ import annotations

# Comprehensive ProcessManager implementation.

# Standard library imports
import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from persistproc.process_types import (
    ListProcessesResult,
    ProcessInfo,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    StartProcessResult,
    StopProcessResult,
    RestartProcessResult,
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


# Interval for the monitor thread (overridable for tests)
_POLL_INTERVAL = float(os.environ.get("PERSISTPROC_TEST_POLL_INTERVAL", "1.0"))


@dataclass
class _ProcEntry:  # noqa: D401 – internal state
    pid: int
    command: list[str]
    working_directory: Optional[str]
    environment: Optional[dict[str, str]]
    start_time: str
    status: str  # running | exited | terminated | failed
    log_prefix: str
    exit_code: Optional[int] = None
    exit_time: Optional[str] = None
    # Keep a reference so we can signal/poll. Excluded from comparisons.
    proc: Optional[subprocess.Popen] = field(repr=False, compare=False, default=None)


class _LogManager:
    """Handle per-process log files & pump threads."""

    @dataclass(slots=True)
    class _LogPaths:  # noqa: D401 – lightweight value object
        stdout: Path
        stderr: Path
        combined: Path

        # Make the instance behave *partly* like a mapping for legacy uses.
        def __getitem__(self, item: str) -> Path:  # noqa: D401 – mapping convenience
            return getattr(self, item)

        def __contains__(self, item: str) -> bool:  # noqa: D401 – mapping convenience
            return hasattr(self, item)

    def __init__(self, base_dir: Path):
        self._dir = base_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------
    # Public helpers
    # -------------------------------

    def paths_for(self, prefix: str) -> _LogPaths:  # noqa: D401
        return self._LogPaths(
            stdout=self._dir / f"{prefix}.stdout",
            stderr=self._dir / f"{prefix}.stderr",
            combined=self._dir / f"{prefix}.combined",
        )

    def start_pumps(self, proc: subprocess.Popen, prefix: str) -> None:  # noqa: D401
        paths = self.paths_for(prefix)

        # open in text mode – we add timestamps manually
        stdout_fh = paths.stdout.open("a", encoding="utf-8")
        stderr_fh = paths.stderr.open("a", encoding="utf-8")
        comb_fh = paths.combined.open("a", encoding="utf-8")

        def _pump(src: subprocess.PIPE, primary, secondary) -> None:  # type: ignore[type-arg]
            # Blocking read; releases GIL.
            for b_line in iter(src.readline, b""):
                line = b_line.decode("utf-8", errors="replace")
                ts_line = f"{_get_iso_ts()} {line}"
                primary.write(ts_line)
                primary.flush()
                secondary.write(ts_line)
                secondary.flush()
            src.close()
            primary.close()

        threading.Thread(
            target=_pump, args=(proc.stdout, stdout_fh, comb_fh), daemon=True
        ).start()
        threading.Thread(
            target=_pump, args=(proc.stderr, stderr_fh, comb_fh), daemon=True
        ).start()

        def _close_combined() -> None:
            proc.wait()
            comb_fh.close()

        threading.Thread(target=_close_combined, daemon=True).start()


class ProcessManager:  # noqa: D101
    def __init__(self) -> None:  # noqa: D401 – simple init
        self.data_dir: Optional[Path] = None
        self._log_dir: Optional[Path] = None
        self._server_log_path: Optional[Path] = None

        self._processes: dict[int, _ProcEntry] = {}
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()

        # monitor thread is started on first *bootstrap*
        self._monitor_thread: Optional[threading.Thread] = None
        self._log_mgr: Optional[_LogManager] = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def bootstrap(
        self, data_dir: Path, server_log_path: Path | None = None
    ) -> None:  # noqa: D401
        """Must be called exactly once after CLI parsed *--data-dir*."""
        self.data_dir = data_dir
        self._log_dir = data_dir / "process_logs"
        self._server_log_path = server_log_path
        self._log_mgr = _LogManager(self._log_dir)

        if self._monitor_thread is None:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True
            )
            self._monitor_thread.start()

        logger.debug("ProcessManager bootstrapped dir=%s", data_dir)

    def shutdown(self) -> None:  # noqa: D401
        """Signal the monitor thread to exit (used by tests)."""
        self._stop_evt.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # Core API – exposed via CLI & MCP tools
    # ------------------------------------------------------------------

    # NOTE: The docstrings are intentionally minimal – rich help is provided
    #       in *tools.py* and the CLI.

    def start_process(
        self,
        command: str,
        working_directory: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> StartProcessResult:  # noqa: D401
        if self._log_mgr is None:
            raise RuntimeError("ProcessManager.bootstrap() must be called first")

        # Prevent duplicate *running* command instances (helps humans)
        with self._lock:
            for ent in self._processes.values():
                # Treat *command* and *working_directory* together as identity so
                # you can run the *same* command from different directories.
                if (
                    ent.command == shlex.split(command)
                    and (ent.working_directory or "")
                    == (str(working_directory) if working_directory else "")
                    and ent.status == "running"
                ):
                    raise ValueError(
                        f"Command '{command}' already running in '{ent.working_directory}' with PID {ent.pid}."
                    )

        if working_directory and not working_directory.is_dir():
            raise ValueError(f"Working directory '{working_directory}' does not exist.")

        try:
            proc = subprocess.Popen(  # noqa: S603 – user command
                shlex.split(command),
                cwd=str(working_directory) if working_directory else None,
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                # Put the child in a different process group so a SIGINT will
                # kill only the child, not the whole process group.
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
        except FileNotFoundError as exc:
            raise ValueError(f"Command not found: {exc.filename}") from exc
        except Exception as exc:  # pragma: no cover – safety net
            raise RuntimeError(f"Failed to start process: {exc}") from exc

        prefix = f"{proc.pid}.{_escape_cmd(command)}"
        self._log_mgr.start_pumps(proc, prefix)

        ent = _ProcEntry(
            pid=proc.pid,
            command=shlex.split(command),
            working_directory=str(working_directory) if working_directory else None,
            environment=environment,
            start_time=_get_iso_ts(),
            status="running",
            log_prefix=prefix,
            proc=proc,
        )

        with self._lock:
            self._processes[proc.pid] = ent

        logger.info("Process %s started", proc.pid)
        logger.debug(
            "event=start_process pid=%s cmd=%s cwd=%s log_prefix=%s",
            proc.pid,
            cmd := " ".join(ent.command),
            ent.working_directory,
            prefix,
        )
        return StartProcessResult(
            pid=proc.pid,
            log_stdout=self._log_mgr.paths_for(prefix).stdout,
            log_stderr=self._log_mgr.paths_for(prefix).stderr,
            log_combined=self._log_mgr.paths_for(prefix).combined,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_processes(self) -> ListProcessesResult:  # noqa: D401
        with self._lock:
            infos = [self._to_public_info(e) for e in self._processes.values()]
        return ListProcessesResult(processes=infos)

    def get_process_status(self, pid: int) -> ProcessStatusResult:  # noqa: D401
        with self._lock:
            ent = self._require(pid)
        logger.debug("event=get_process_status pid=%s status=%s", pid, ent.status)
        return ProcessStatusResult(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory or "",
            status=ent.status,
        )

    # ------------------------------------------------------------------
    # Control helpers
    # ------------------------------------------------------------------

    def stop_process(
        self,
        pid: int | None = None,
        command: str | None = None,
        working_directory: Path | None = None,
        force: bool = False,
    ) -> StopProcessResult:  # noqa: D401
        if pid is None and command is None:
            return StopProcessResult(
                error="Either pid or command must be provided to stop_process"
            )

        if command is not None:
            found_pid = None
            with self._lock:
                for p_ent in self._processes.values():
                    if (
                        p_ent.command == shlex.split(command)
                        and (p_ent.working_directory or "")
                        == (str(working_directory) if working_directory else "")
                        and p_ent.status == "running"
                    ):
                        found_pid = p_ent.pid
                        break
            if not found_pid:
                return StopProcessResult(
                    error=f"Command '{command}' not found running in '{working_directory}'."
                )
            pid = found_pid

        if pid is None:
            # Should be unreachable
            return StopProcessResult(error="Could not identify process to stop.")

        ent = self._require(pid)

        if ent.status != "running":
            return StopProcessResult(exit_code=ent.exit_code or 0)

        timeout = 8.0  # XXX TIMEOUT – graceful wait
        exited = self._wait_for_exit(ent.proc, timeout)
        if not exited and not force:
            # Escalate to SIGKILL once and wait briefly.
            try:
                self._send_signal(pid, signal.SIGKILL)
                logger.warning("Escalated to SIGKILL pid=%s", pid)
            except ProcessLookupError:
                pass  # Process vanished between checks.

            exited = self._wait_for_exit(ent.proc, 2.0)  # XXX TIMEOUT – short

        if not exited:
            logger.error("event=stop_timeout pid=%s", pid)
            return StopProcessResult(error="timeout")

        # Process exited – record metadata.
        with self._lock:
            ent.status = "terminated"
            ent.proc = None
            if ent.exit_code is None:
                ent.exit_code = 0
            ent.exit_time = _get_iso_ts()

        logger.debug("event=stopped pid=%s exit_code=%s", pid, ent.exit_code)
        return StopProcessResult(exit_code=ent.exit_code)

    def restart_process(
        self,
        pid: int | None = None,
        command: str | None = None,
        working_directory: Path | None = None,
    ) -> RestartProcessResult:  # noqa: D401
        """Attempt to stop then start *pid*.

        On success returns ``RestartProcessResult(pid=new_pid)`` for parity with
        :py:meth:`stop_process`.  If stopping timed-out the same
        ``RestartProcessResult`` with ``error='timeout'`` is propagated so callers
        can decide how to handle the failure.
        """
        if pid is None and command is None:
            return RestartProcessResult(
                error="Either pid or command must be provided to restart_process"
            )

        ent: _ProcEntry | None = None
        original_pid = pid

        if pid is not None:
            with self._lock:
                if pid not in self._processes:
                    return RestartProcessResult(error=f"PID {pid} not found")
                ent = self._processes[pid]
        else:  # command is not None
            with self._lock:
                for p_ent in self._processes.values():
                    if (
                        p_ent.command == shlex.split(command)
                        and (p_ent.working_directory or "")
                        == (str(working_directory) if working_directory else "")
                        and p_ent.status == "running"
                    ):
                        ent = p_ent
                        break
            if not ent:
                return RestartProcessResult(
                    error=f"Command '{command}' not found running in '{working_directory}'."
                )
            pid = ent.pid

        if ent is None or pid is None:
            # This should be unreachable due to the checks above, but satisfies mypy.
            return RestartProcessResult(error="Could not identify process to restart.")

        cmd = " ".join(ent.command)
        cwd = Path(ent.working_directory) if ent.working_directory else None
        env = ent.environment

        stop_res = self.stop_process(pid, force=False)
        if stop_res.error is not None:
            # Forward failure.
            return RestartProcessResult(error=stop_res.error)

        start_res = self.start_process(cmd, working_directory=cwd, environment=env)

        logger.debug("event=restart pid_old=%s pid_new=%s", original_pid, start_res.pid)

        return RestartProcessResult(pid=start_res.pid)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def get_process_output(
        self,
        pid: int,
        stream: str,
        lines: Optional[int] = None,
        before_time: Optional[str] = None,
        since_time: Optional[str] = None,
    ) -> ProcessOutputResult:  # noqa: D401
        if self._log_mgr is None:
            raise RuntimeError("ProcessManager not bootstrapped")

        if pid == 0:
            # Special case – read the main CLI/server log file if known.
            if self._server_log_path and self._server_log_path.exists():
                with self._server_log_path.open("r", encoding="utf-8") as fh:
                    all_lines = fh.readlines()
                return ProcessOutputResult(output=all_lines)
            return ProcessOutputResult(output=[])  # Unknown path – empty

        ent = self._require(pid)
        paths = self._log_mgr.paths_for(ent.log_prefix)
        if stream not in paths:
            raise ValueError("stream must be stdout|stderr|combined")
        path = paths[stream]
        if not path.exists():
            return ProcessOutputResult(output=[])

        with path.open("r", encoding="utf-8") as fh:
            all_lines = fh.readlines()

        # Optional ISO filtering (copied from previous implementation)
        def _parse_iso(ts: str) -> datetime:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)

        if since_time:
            since_dt = _parse_iso(since_time)
            all_lines = [
                ln for ln in all_lines if _parse_iso(ln.split(" ", 1)[0]) >= since_dt
            ]
        if before_time:
            before_dt = _parse_iso(before_time)
            all_lines = [
                ln for ln in all_lines if _parse_iso(ln.split(" ", 1)[0]) < before_dt
            ]

        if lines is not None:
            all_lines = all_lines[-lines:]

        return ProcessOutputResult(output=all_lines)

    def get_process_log_paths(self, pid: int) -> ProcessLogPathsResult:  # noqa: D401
        ent = self._require(pid)
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
                    self.stop_process(ent.pid, force=True)
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

    def _require(self, pid: int) -> _ProcEntry:  # noqa: D401 – helper
        with self._lock:
            if pid not in self._processes:
                raise ValueError(f"PID {pid} not found")
            return self._processes[pid]

    def _to_public_info(self, ent: _ProcEntry) -> ProcessInfo:  # noqa: D401 – helper
        return ProcessInfo(
            pid=ent.pid,
            command=ent.command,
            working_directory=ent.working_directory or "",
            status=ent.status,
        )

    def _monitor_loop(self) -> None:  # noqa: D401 – thread target
        while not self._stop_evt.is_set():
            logger.debug("event=monitor_tick_start num_procs=%s", len(self._processes))
            with self._lock:
                running = [e for e in self._processes.values() if e.status == "running"]
            for ent in running:
                if ent.proc is None:
                    continue
                code = ent.proc.poll()
                if code is not None:
                    ent.exit_code = code
                    ent.exit_time = _get_iso_ts()
                    ent.status = "exited" if code == 0 else "failed"
                    ent.proc = None
                    logger.debug(
                        "event=proc_exit pid=%s code=%s status=%s",
                        ent.pid,
                        code,
                        ent.status,
                    )
            time.sleep(_POLL_INTERVAL)
            logger.debug("event=monitor_tick_end")

    # ------------------ signal helpers ------------------

    @staticmethod
    def _send_signal(pid: int, sig: signal.Signals) -> None:  # noqa: D401
        if os.name == "nt":
            # Windows – no process groups, best-effort
            os.kill(pid, sig.value)  # type: ignore[attr-defined]
        else:
            os.killpg(os.getpgid(pid), sig)  # type: ignore[arg-type]

    @staticmethod
    def _wait_for_exit(
        proc: Optional[subprocess.Popen], timeout: float
    ) -> bool:  # noqa: D401
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
