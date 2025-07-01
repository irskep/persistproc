import argparse
import asyncio
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Dict, List, Literal, Optional

from fastmcp import FastMCP
from fastmcp.client import Client


# --- App Data Setup ---
def get_app_data_dir(app_name: str) -> Path:
    """Gets the platform-specific application data directory."""
    if sys.platform == "darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / app_name
    elif sys.platform.startswith("linux"):  # Linux
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / app_name
        return Path.home() / ".local" / "share" / app_name
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    # Fallback for other operating systems
    return Path.home() / f".{app_name}"


APP_NAME = "persistproc"
APP_DATA_DIR = get_app_data_dir(APP_NAME)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Constants ---
LOG_DIRECTORY = APP_DATA_DIR / "logs"
MAX_COMMAND_LEN = 50

# --- Logging Setup ---
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging with custom format showing only level and message."""
    level = logging.DEBUG if verbose else logging.INFO

    # Get our specific logger
    log = logging.getLogger(__name__)
    log.setLevel(level)
    log.propagate = False  # Prevent duplicate logs in root logger
    if log.hasHandlers():
        log.handlers.clear()

    # Console handler with simple format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(console_handler)

    # File handler for persistproc.log with detailed, ISO-formatted timestamps
    log_file_path = LOG_DIRECTORY / "persistproc.log"
    file_handler = logging.FileHandler(log_file_path)
    iso_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    iso_formatter.converter = time.gmtime
    file_handler.setFormatter(iso_formatter)
    log.addHandler(file_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    # Let fastmcp log to console, but not to our file
    logging.getLogger("fastmcp").propagate = True
    logging.getLogger("fastmcp").setLevel(logging.INFO)


# --- Data Structures ---
@dataclass
class ProcessInfo:
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


# --- Utility Functions ---
def get_iso_timestamp() -> str:
    """Returns the current UTC time in ISO 8601 format."""
    # Use timezone-aware datetime objects as recommended to avoid DeprecationWarning
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def escape_command(command: str) -> str:
    """Sanitizes and truncates a command string for use in filenames."""
    escaped = re.sub(r"\s+", "_", command)
    escaped = re.sub(r"[^a-zA-Z0-9_-]", "", escaped)
    return escaped[:MAX_COMMAND_LEN]


# --- Core Components ---
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
        files_to_open = [
            (log_paths["stdout"], [proc.stdout]),
            (log_paths["stderr"], [proc.stderr]),
            (log_paths["combined"], [proc.stdout, proc.stderr]),  # For unified log
        ]

        # We'll have two threads writing to three files.
        # One for stdout, one for stderr. Both will also write to combined.

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
        log_file: Optional[Path] = None
        if pid == 0:
            # PID 0 is a special case for the main server log.
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


# --- Global Instance ---
process_manager: ProcessManager


# --- MCP App Setup ---
def create_app():
    """Create and configure the FastMCP app with tools."""
    app = FastMCP("persistproc")

    @app.tool()
    def start_process(
        command: str, working_directory: str = None, environment: dict = None
    ) -> str:
        """Start a new long-running process."""
        logger.debug(f"start_process called with command: {command}")
        try:
            result = process_manager.start_process(
                command, working_directory, environment
            )
            logger.debug(f"start_process result: {result}")
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            logger.error(f"start_process error: {e}")
            return json.dumps({"error": str(e)})

    @app.tool()
    def stop_process(pid: int, force: bool = False) -> str:
        """Stop a running process by its PID."""
        logger.debug(f"stop_process called with pid: {pid}, force: {force}")
        try:
            result = process_manager.stop_process(pid, force)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def list_processes() -> str:
        """List all managed processes and their status."""
        logger.debug("list_processes called")
        try:
            result = process_manager.list_processes()
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_status(pid: int) -> str:
        """Get the detailed status of a specific process."""
        logger.debug(f"get_process_status called with pid: {pid}")
        try:
            result = process_manager.get_process_status(pid)
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_output(
        pid: int,
        stream: str,
        lines: int = None,
        before_time: str = None,
        since_time: str = None,
    ) -> str:
        """
        Retrieve captured output from a process.
        Can fetch the last N lines, and/or lines before/since a given ISO8601 timestamp.
        Use PID 0 to retrieve the main persistproc server log; the 'stream' parameter is ignored in this case.
        """
        logger.debug(
            f"get_process_output called with pid: {pid}, stream: {stream}, lines: {lines}, before_time: {before_time}, since_time: {since_time}"
        )
        try:
            result = process_manager.get_process_output(
                pid, stream, lines, before_time, since_time
            )
            return json.dumps(result, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def get_process_log_paths(pid: int) -> str:
        """Get the paths to the log files for a specific process."""
        logger.debug(f"get_process_log_paths called with pid: {pid}")
        try:
            with process_manager.lock:
                p_info = process_manager.processes.get(pid)
            if not p_info:
                raise ValueError(f"Process with PID {pid} not found.")

            log_paths = process_manager.log_manager.get_log_paths(p_info.log_prefix)
            # convert Path objects to strings for JSON serialization
            str_log_paths = {k: str(v) for k, v in log_paths.items()}
            return json.dumps(str_log_paths, indent=2)
        except (ValueError, RuntimeError) as e:
            return json.dumps({"error": str(e)})

    @app.tool()
    def restart_process(pid: int) -> str:
        """Stops a process and starts it again with the same parameters."""
        logger.debug(f"restart_process called with pid: {pid}")
        try:
            # Get old process info
            p_info_dict = process_manager.get_process_status(pid)

            command = p_info_dict["command"]
            wd = p_info_dict.get("working_directory")
            env = p_info_dict.get("environment")

            # Stop old process
            process_manager.stop_process(pid)

            # Start new process
            new_p_info_dict = process_manager.start_process(command, wd, env)
            return json.dumps(new_p_info_dict, indent=2)

        except (ValueError, RuntimeError) as e:
            logger.error(f"restart_process error: {e}")
            return json.dumps({"error": str(e)})

    return app


def parse_args():
    parser = argparse.ArgumentParser(
        description="PersistProc: Manage and monitor long-running processes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the MCP server in the background
  persistproc --serve &

  # Run a command and tail its output
  persistproc sleep 30

  # Run a command with quotes and tail its output
  persistproc "python -m http.server"
""",
    )
    parser.add_argument(
        "--serve", action="store_true", help="Run the PersistProc MCP server."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to connect to or bind to."
    )
    parser.add_argument(
        "--port", type=int, default=8947, help="Port to connect to or bind to."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run and monitor.",
    )
    return parser, parser.parse_args()


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        # Stop all running processes
        for pid, p_info in process_manager.processes.items():
            if p_info.status == "running":
                try:
                    process_manager.stop_process(pid)
                    logger.info(f"Stopped process {pid}")
                except Exception as e:
                    logger.error(f"Error stopping process {pid}: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def run_and_tail_async(args: argparse.Namespace):
    """
    Client-side function to start a process via the server and tail its logs.
    """
    if not args.command:
        logger.error("No command provided to run.")
        return

    command_str = " ".join(args.command)
    mcp_url = f"http://{args.host}:{args.port}/mcp/"

    try:
        client = Client(mcp_url)
        async with client:
            # 1. Start the process
            logger.debug(f"Requesting to start command: '{command_str}'")
            start_result = await client.call_tool(
                "start_process",
                {"command": command_str, "working_directory": os.getcwd()},
            )

            p_info_str = start_result[0].text
            p_info = json.loads(p_info_str)

            if "error" in p_info:
                error_msg = p_info["error"]
                if "is already running with PID" in error_msg:
                    pid_match = re.search(r"PID (\d+)", error_msg)
                    if pid_match:
                        existing_pid = int(pid_match.group(1))
                        p_info = await handle_existing_process(
                            client, existing_pid, command_str
                        )
                    else:
                        logger.error(f"Server returned an error: {error_msg}")
                        sys.exit(1)
                else:
                    logger.error(
                        f"Server returned an error on start: {p_info['error']}"
                    )
                    sys.exit(1)

            pid = p_info.get("pid")
            if not pid:
                logger.error(f"Could not get PID from server response: {p_info_str}")
                sys.exit(1)

            logger.info(f"Process started with PID: {pid}")

            # 2. Get log path
            logs_result = await client.call_tool("get_process_log_paths", {"pid": pid})
            log_paths_str = logs_result[0].text
            if "error" in log_paths_str:
                log_paths = json.loads(log_paths_str)
                logger.error(
                    f"Server returned an error on get_process_log_paths: {log_paths['error']}"
                )
                sys.exit(1)

            log_paths = json.loads(log_paths_str)
            combined_log_path = Path(log_paths["combined"])

            # 3. Tail the log file
            await tail_and_monitor_process_async(
                client, pid, command_str, combined_log_path
            )

    except Exception as e:
        logger.error(
            f"Failed to connect to persistproc server at {mcp_url}. Is it running with '--serve'?"
        )
        logger.debug(f"Connection details: {e}")
        sys.exit(1)


async def handle_existing_process(client: Client, pid: int, command_str: str) -> Dict:
    """
    Handles the interactive workflow when a process already exists.
    Returns the process info dict to tail. This function loops until a valid choice is made.
    """
    while True:
        choice = (
            input(
                f"\nProcess '{command_str}' is already running with PID {pid}.\n"
                "Choose an action: [T]ail existing, [R]estart\n"
                "> "
            )
            .lower()
            .strip()
        )

        if choice in ["t", "tail"]:
            logger.info(f"Tailing existing process {pid}.")
            status_result = await client.call_tool("get_process_status", {"pid": pid})
            return json.loads(status_result[0].text)

        elif choice in ["r", "restart"]:
            logger.info(f"Requesting restart for process {pid}...")
            restart_result = await client.call_tool("restart_process", {"pid": pid})
            p_info_str = restart_result[0].text
            p_info = json.loads(p_info_str)
            if "error" in p_info:
                logger.error(f"Error restarting process: {p_info['error']}")
                sys.exit(1)
            new_pid = p_info.get("pid")
            logger.info(f"Process restarted with new PID: {new_pid}")
            return p_info
        else:
            print("Invalid choice. Please try again.")


async def tail_and_monitor_process_async(
    client: Client, pid: int, command_str: str, log_path: Path
):
    """Tails a log file while monitoring the corresponding process for completion."""
    while not log_path.exists():
        await asyncio.sleep(0.1)

    log_file = log_path.open("r")

    print(f"--- Tailing output for PID {pid} ('{command_str}') ---", file=sys.stderr)
    print(f"--- Log file: {log_path} ---", file=sys.stderr)

    stop_event = threading.Event()

    def tail_worker():
        # First, print any existing content in the file
        for line in log_file:
            sys.stdout.write(line)
        sys.stdout.flush()

        # Now, tail for new content
        while not stop_event.is_set():
            line = log_file.readline()
            if not line:
                time.sleep(0.1)  # Avoid busy-waiting
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
        log_file.close()

    tail_thread = threading.Thread(target=tail_worker, daemon=True)
    tail_thread.start()

    try:
        # Monitor process status in the main async task
        while tail_thread.is_alive():
            try:
                status_result = await client.call_tool(
                    "get_process_status", {"pid": pid}
                )
                p_status = json.loads(status_result[0].text)
                if "error" in p_status or p_status.get("status") != "running":
                    break
            except Exception as e:
                logger.debug(f"Could not poll process status: {e}")
                break  # Stop if we can't talk to the server

            await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\n--- Caught interrupt, stopping process... ---", file=sys.stderr)
        try:
            await client.call_tool("stop_process", {"pid": pid, "force": False})
            print(f"--- Sent stop request for PID {pid} ---", file=sys.stderr)
        except Exception as e:
            logger.error(f"Could not stop process {pid}: {e}", file=sys.stderr)
    finally:
        stop_event.set()
        tail_thread.join(timeout=2)


def main():
    """Parses arguments and runs the appropriate application mode."""
    global process_manager
    parser, args = parse_args()
    setup_logging(args.verbose)

    if args.command:
        asyncio.run(run_and_tail_async(args))
    elif args.serve:
        logger.info("--- PersistProc Server Starting ---")
        logger.info(f"Log directory: {LOG_DIRECTORY.resolve()}")

        logger.debug(f"Initializing ProcessManager with log_directory={LOG_DIRECTORY}")
        process_manager = ProcessManager(LOG_DIRECTORY)

        logger.debug("Creating FastMCP app")
        app = create_app()

        logger.debug("Setting up signal handlers")
        setup_signal_handlers()

        logger.info(f"Starting PersistProc MCP Server on {args.host}:{args.port}")
        app.run(transport="http", host=args.host, port=args.port, path="/mcp/")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
