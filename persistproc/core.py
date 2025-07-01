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

        self.monitor_thread = threading.Thread(
            target=self._monitor_processes, daemon=True
        )
        self.monitor_thread.start()

    def _log_event(self, p_info: ProcessInfo, message: str):
        logger.info(f"AUDIT (PID {p_info.pid}): {message}")
        log_paths = self.log_manager.get_log_paths(p_info.log_prefix)
        with log_paths["combined"].open("a") as f:
            f.write(f"[{get_iso_timestamp()}] [SYSTEM] {message}\n")

    def _monitor_processes(self):
        while True:
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
            time.sleep(1)

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

        try:
            proc = subprocess.Popen(
                shlex.split(command),
                cwd=working_directory,
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                preexec_fn=os.setsid if os.name == "posix" else None,
            )
        except FileNotFoundError as e:
            raise ValueError(f"Command not found: {e.filename}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to start process: {e}") from e

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

    def stop_process(self, pid: int, force: bool = False) -> Dict:
        with self.lock:
            p_info = self.processes.get(pid)

        if not p_info:
            raise ValueError(f"Process with PID {pid} not found.")
        if p_info.status != "running":
            raise ValueError(f"Process {pid} is not running (status: {p_info.status}).")

        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.killpg(os.getpgid(pid), sig)
            self._log_event(p_info, f"Sent signal {sig.name} to process group {pid}.")
        except ProcessLookupError:
            self._log_event(p_info, "Process was already gone when stop was requested.")
        except Exception as e:
            raise RuntimeError(f"Failed to send signal to process {pid}: {e}")

        with self.lock:
            p_info.status = "terminated"

        return process_info_to_dict(p_info)

    def list_processes(self) -> List[Dict]:
        with self.lock:
            return [process_info_to_dict(p) for p in self.processes.values()]

    def get_process_status(self, pid: int) -> Dict:
        with self.lock:
            p_info = self.processes.get(pid)
        if not p_info:
            raise ValueError(f"Process with PID {pid} not found.")
        return process_info_to_dict(p_info)

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
