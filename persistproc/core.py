"""
Core process management components.

This module contains the main ProcessManager and LogManager classes,
along with data structures for process information.
"""

import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, IO

from .utils import get_iso_timestamp, escape_command

logger = logging.getLogger("persistproc")

POLL_INTERVAL = float(os.environ.get("PERSISTPROC_TEST_POLL_INTERVAL", "1.0"))


@dataclass
class ProcessInfo:
    """Information about a managed process."""

    pid: int
    command: str
    start_time: str
    status: Literal["running", "exited", "terminated", "failed"]
    log_prefix: str
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None
    exit_code: Optional[int] = None
    exit_time: Optional[str] = None
    proc: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)


class LogManager:
    """Manages log file creation and writing."""

    def __init__(self, log_directory: Path):
        self.log_directory = log_directory
        self.log_directory.mkdir(exist_ok=True)

    def get_log_paths(self, log_prefix: str) -> Dict[str, Path]:
        return {
            "stdout": self.log_directory / f"{log_prefix}.stdout",
            "stderr": self.log_directory / f"{log_prefix}.stderr",
            "combined": self.log_directory / f"{log_prefix}.combined",
        }

    def start_logging(self, proc: subprocess.Popen, log_prefix: str):
        log_paths = self.get_log_paths(log_prefix)

        # Open files in append mode
        stdout_log_file = log_paths["stdout"].open("a")
        stderr_log_file = log_paths["stderr"].open("a")
        combined_log_file = log_paths["combined"].open("a")

        def log_stream(stream: IO[bytes], primary_log: IO, secondary_log: IO):
            for line_bytes in iter(stream.readline, b""):
                line = line_bytes.decode("utf-8", errors="replace")
                timestamped_line = f"{get_iso_timestamp()} {line}"
                primary_log.write(timestamped_line)
                primary_log.flush()
                secondary_log.write(timestamped_line)
                secondary_log.flush()
            stream.close()
            primary_log.close()

        # Stdout logging thread
        threading.Thread(
            target=log_stream,
            args=(proc.stdout, stdout_log_file, combined_log_file),
            daemon=True,
        ).start()

        # Stderr logging thread
        threading.Thread(
            target=log_stream,
            args=(proc.stderr, stderr_log_file, combined_log_file),
            daemon=True,
        ).start()

        # A separate thread to close the combined log file when both streams are done.
        def combined_log_closer():
            proc.wait()  # Wait for process to finish
            combined_log_file.close()

        threading.Thread(target=combined_log_closer, daemon=True).start()


class ProcessManager:
    """The central coordinator for all process lifecycle operations."""

    def __init__(self, log_directory: Path):
        self.log_directory = log_directory
        self.log_manager = LogManager(self.log_directory)
        self.processes: Dict[int, ProcessInfo] = {}
        self.lock = threading.Lock()
        self._stop_monitor = threading.Event()

        self.monitor_thread = threading.Thread(
            target=self._monitor_processes, daemon=True
        )
        self.monitor_thread.start()

    def stop_monitor_thread(self):
        """Signals the monitor thread to stop."""
        self._stop_monitor.set()
        self.monitor_thread.join(timeout=2)

    def _log_event(self, p_info: ProcessInfo, message: str):
        logger.info(f"AUDIT (PID {p_info.pid}): {message}")
        log_paths = self.log_manager.get_log_paths(p_info.log_prefix)
        with log_paths["combined"].open("a") as f:
            f.write(f"[{get_iso_timestamp()}] [SYSTEM] {message}\n")

    def _monitor_processes(self):
        while not self._stop_monitor.is_set():
            with self.lock:
                running_procs = {
                    pid: p for pid, p in self.processes.items() if p.status == "running"
                }

            for pid, p_info in running_procs.items():
                if p_info.proc:
                    exit_code = p_info.proc.poll()
                    if exit_code is not None:
                        with self.lock:
                            p_info.exit_code = exit_code
                            p_info.exit_time = get_iso_timestamp()
                            p_info.status = "exited" if exit_code == 0 else "failed"
                            p_info.proc = None
                            self._log_event(
                                p_info, f"Process exited with code {exit_code}."
                            )
            time.sleep(POLL_INTERVAL)

    def _create_subprocess(
        self,
        command: str,
        working_directory: Optional[str],
        environment: Optional[Dict[str, str]],
    ) -> subprocess.Popen:
        """Creates and returns a new subprocess."""
        try:
            return subprocess.Popen(
                shlex.split(command),
                cwd=working_directory,
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError as e:
            raise ValueError(f"Command not found: {e.filename}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to start process: {e}") from e

    def start_process(
        self,
        command: str,
        working_directory: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> Dict:
        with self.lock:
            for p_info in self.processes.values():
                if p_info.command == command and p_info.status == "running":
                    raise ValueError(
                        f"A process with command '{command}' is already running with PID {p_info.pid}."
                    )

        if working_directory and not Path(working_directory).is_dir():
            raise ValueError(f"Working directory '{working_directory}' does not exist.")

        proc = self._create_subprocess(command, working_directory, environment)

        escaped_cmd = escape_command(command)
        log_prefix = f"{proc.pid}.{escaped_cmd}"

        self.log_manager.start_logging(proc, log_prefix)

        log_paths = self.log_manager.get_log_paths(log_prefix)
        logger.info(f"Process {proc.pid} logging to:")
        for name, path in log_paths.items():
            logger.info(f"  {name}: {path}")

        p_info = ProcessInfo(
            pid=proc.pid,
            command=command,
            start_time=get_iso_timestamp(),
            status="running",
            log_prefix=log_prefix,
            working_directory=working_directory,
            environment=environment,
            proc=proc,
        )

        with self.lock:
            self.processes[proc.pid] = p_info

        self._log_event(p_info, f"Process started with command: {command}")
        return process_info_to_dict(p_info)

    def _perform_graceful_shutdown(
        self, p_info: ProcessInfo, force: bool, timeout: Optional[float]
    ):
        """Handles the graceful shutdown sequence with optional force kill."""
        pid = p_info.pid
        try:
            graceful_sig = signal.SIGKILL if force else signal.SIGTERM
            self._send_signal(pid, graceful_sig)
            self._log_event(
                p_info, f"Sent signal {graceful_sig.name} to process group {pid}."
            )
        except ProcessLookupError:
            self._log_event(p_info, "Process was already gone when stop was requested.")
            with self.lock:
                p_info.status = "terminated"
            return
        except Exception as e:
            raise RuntimeError(f"Failed to send signal to process {pid}: {e}")

        # Wait for graceful exit. Use custom timeout if provided.
        graceful_timeout = 8 if timeout is None else timeout

        if not self._wait_for_exit(p_info.proc, timeout=graceful_timeout):
            if force:
                self._log_event(p_info, "Process did not exit after SIGKILL timeout.")
            else:
                # Escalate to SIGKILL
                self._log_event(
                    p_info, f"Escalated to SIGKILL for process group {pid}."
                )
                try:
                    self._send_signal(pid, signal.SIGKILL)
                    if not self._wait_for_exit(p_info.proc, timeout=2):
                        self._log_event(
                            p_info,
                            "Timed-out waiting for process to exit after SIGKILL.",
                        )
                except ProcessLookupError:
                    pass  # Gone in between

    def stop_process(
        self, pid: int, force: bool = False, timeout: Optional[float] = None
    ) -> Dict:
        with self.lock:
            p_info = self.processes.get(pid)

        if not p_info:
            raise ValueError(f"Process with PID {pid} not found.")

        # If the process isn't running, just return its current state.
        # This makes the function idempotent and avoids race conditions.
        if p_info.status != "running":
            logger.warning(
                f"Stop called on non-running process {pid} (status: {p_info.status}). Returning current state."
            )
            return process_info_to_dict(p_info)

        self._perform_graceful_shutdown(p_info, force, timeout)

        # Clean up proc reference and update status
        with self.lock:
            p_info.proc = None
            p_info.status = (
                "terminated" if p_info.status == "running" else p_info.status
            )

        return process_info_to_dict(p_info)

    def restart_process(self, pid: int) -> Dict:
        """Stops and restarts a process by its PID."""
        p_info = self.get_process_status(pid)  # This also validates the PID
        command = p_info["command"]
        wd = p_info.get("working_directory")
        env = p_info.get("environment")

        self.stop_process(pid)

        # It's possible for the process to be "running" but the OS process
        # to be gone. In that case, start_process would fail with a duplicate
        # command error. We add a small delay to let the monitor thread catch up.
        time.sleep(0.1)

        return self.start_process(command, wd, env)

    def list_processes(self) -> List[Dict]:
        """Returns a list of all managed processes."""
        with self.lock:
            return [process_info_to_dict(p) for p in self.processes.values()]

    def get_process_status(self, pid: int) -> Dict:
        with self.lock:
            p_info = self.processes.get(pid)
        if not p_info:
            raise ValueError(f"Process with PID {pid} not found.")
        return process_info_to_dict(p_info)

    def get_log_paths(self, pid: int) -> Dict[str, str]:
        """Gets the log file paths for a specific process."""
        with self.lock:
            p_info = self.processes.get(pid)
        if not p_info:
            raise ValueError(f"Process with PID {pid} not found.")

        log_paths = self.log_manager.get_log_paths(p_info.log_prefix)
        # convert Path objects to strings for JSON serialization
        return {k: str(v) for k, v in log_paths.items()}

    def get_process_output(
        self,
        pid: int,
        stream: str,
        lines: Optional[int] = None,
        before_time: Optional[str] = None,
        since_time: Optional[str] = None,
    ) -> List[str]:
        from .utils import get_app_data_dir

        log_file: Optional[Path] = None
        if pid == 0:
            # PID 0 is a special case for the main server log.
            APP_DATA_DIR = get_app_data_dir("persistproc")
            LOG_DIRECTORY = APP_DATA_DIR / "logs"
            log_file = LOG_DIRECTORY / "persistproc.log"
        else:
            if stream not in ["stdout", "stderr", "combined"]:
                raise ValueError("Stream must be 'stdout', 'stderr', or 'combined'.")

            with self.lock:
                p_info = self.processes.get(pid)
            if not p_info:
                raise ValueError(f"Process with PID {pid} not found.")

            log_paths = self.log_manager.get_log_paths(p_info.log_prefix)
            log_file = log_paths.get(stream)

        if not log_file or not log_file.exists():
            return []

        with log_file.open("r") as f:
            all_lines = f.readlines()

        if since_time:
            try:
                if since_time.endswith("Z"):
                    since_time = since_time[:-1] + "+00:00"
                since_dt = datetime.fromisoformat(since_time)
            except ValueError:
                raise ValueError(
                    f"Invalid ISO8601 timestamp format for since_time: {since_time}"
                )

            filtered_lines = []
            for line in all_lines:
                try:
                    line_ts_str = line.split(" ", 1)[0]
                    if line_ts_str.endswith("Z"):
                        line_ts_str = line_ts_str[:-1] + "+00:00"
                    line_dt = datetime.fromisoformat(line_ts_str)
                    if line_dt >= since_dt:
                        filtered_lines.append(line)
                except (ValueError, IndexError):
                    continue  # Ignore lines without a valid timestamp
            all_lines = filtered_lines

        if before_time:
            try:
                if before_time.endswith("Z"):
                    before_time = before_time[:-1] + "+00:00"
                before_dt = datetime.fromisoformat(before_time)
            except ValueError:
                raise ValueError(
                    f"Invalid ISO8601 timestamp format for before_time: {before_time}"
                )

            filtered_lines = []
            for line in all_lines:
                try:
                    line_ts_str = line.split(" ", 1)[0]
                    if line_ts_str.endswith("Z"):
                        line_ts_str = line_ts_str[:-1] + "+00:00"
                    line_dt = datetime.fromisoformat(line_ts_str)
                    if line_dt < before_dt:
                        filtered_lines.append(line)
                except (ValueError, IndexError):
                    continue  # Ignore lines without a valid timestamp
            all_lines = filtered_lines

        if lines:
            return all_lines[-lines:]

        return all_lines

    # --- Internal helpers -------------------------------------------------

    def _send_signal(self, pid: int, sig: signal.Signals):
        """Send *sig* to the process group rooted at *pid* (Unix only)."""
        os.killpg(os.getpgid(pid), sig)

    def _wait_for_exit(self, proc: Optional[subprocess.Popen], timeout: float) -> bool:
        """Return True if *proc* terminates within *timeout* seconds."""
        if proc is None:
            # We no longer track the process object; assume gone.
            return True
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False


def process_info_to_dict(p_info: ProcessInfo) -> dict:
    """Convert ProcessInfo to a clean dictionary without non-serializable objects."""
    return {
        "pid": p_info.pid,
        "command": p_info.command,
        "start_time": p_info.start_time,
        "status": p_info.status,
        "log_prefix": p_info.log_prefix,
        "working_directory": p_info.working_directory,
        "environment": p_info.environment,
        "exit_code": p_info.exit_code,
        "exit_time": p_info.exit_time,
    }
