"""
Client-side CLI and log tailing functionality.

This module contains the command-line interface code for connecting
to the MCP server and tailing process logs.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from fastmcp.client import Client

logger = logging.getLogger("persistproc")

# Constants for log processing
TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PersistProc: Manage and monitor long-running processes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Global arguments
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to connect to or bind to."
    )
    parser.add_argument(
        "--port", type=int, default=8947, help="Port to connect to or bind to."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # --- Server Command ---
    parser_serve = subparsers.add_parser(
        "serve", help="Run the PersistProc MCP server."
    )

    # --- Run Command ---
    parser_run = subparsers.add_parser("run", help="Run a command and tail its output.")
    parser_run.add_argument(
        "--restart",
        action="store_true",
        help="Restart the process if it's already running.",
    )
    parser_run.add_argument(
        "--raw",
        action="store_true",
        help="Display the raw, timestamped log file content instead of the clean process output.",
    )
    parser_run.add_argument(
        "--on-exit",
        choices=["stop", "detach", "ask"],
        default="ask",
        help="What to do when Ctrl+C is pressed. 'stop' will stop the process, 'detach' will leave it running. 'ask' will prompt you. Default is 'ask'.",
    )
    parser_run.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run and monitor.",
    )

    # --- Tool Commands ---
    parser_list = subparsers.add_parser(
        "list", help="List all managed processes and their status."
    )
    parser_status = subparsers.add_parser(
        "status", help="Get the detailed status of a specific process."
    )
    parser_status.add_argument("pid", type=int, help="The PID of the process.")

    parser_stop = subparsers.add_parser(
        "stop", help="Stop a running process by its PID."
    )
    parser_stop.add_argument("pid", type=int, help="The PID of the process.")
    parser_stop.add_argument(
        "--force", action="store_true", help="Force stop the process (SIGKILL)."
    )

    parser_restart = subparsers.add_parser(
        "restart", help="Restart a running process by its PID."
    )
    parser_restart.add_argument("pid", type=int, help="The PID of the process.")

    parser_output = subparsers.add_parser(
        "output", help="Retrieve captured output from a process."
    )
    parser_output.add_argument("pid", type=int, help="The PID of the process.")
    parser_output.add_argument(
        "stream",
        choices=["stdout", "stderr", "combined"],
        help="The output stream to retrieve.",
    )
    parser_output.add_argument(
        "--lines", type=int, help="The number of lines to retrieve from the end."
    )

    parser_log_paths = subparsers.add_parser(
        "log-paths", help="Get the paths to the log files for a process."
    )
    parser_log_paths.add_argument(
        "pid_or_command",
        help="The PID or the exact command string of the process.",
    )

    return parser, parser.parse_args()


async def tool_command_wrapper(args, tool_name, params=None):
    """A generic wrapper to connect, call a tool, and print the result."""
    mcp_url = f"http://{args.host}:{args.port}/mcp/"
    try:
        async with Client(mcp_url) as client:
            result = await client.call_tool(tool_name, params or {})
            # Pretty print JSON for most tools
            try:
                data = json.loads(result[0].text)
                print(json.dumps(data, indent=2))
            except json.JSONDecodeError:
                print(result[0].text)
    except Exception as e:
        logger.error(f"Failed to connect to persistproc server at {mcp_url}.")
        logger.debug(f"Connection error: {e}")
        sys.exit(1)


async def log_paths_command(args: argparse.Namespace):
    """Handles the 'log-paths' command."""
    mcp_url = f"http://{args.host}:{args.port}/mcp/"
    pid_or_command = args.pid_or_command
    pid_to_use = None

    try:
        pid_to_use = int(pid_or_command)
    except ValueError:
        # Not a PID, so it must be a command string
        pass

    try:
        async with Client(mcp_url) as client:
            if pid_to_use is None:
                # It's a command string, we need to find the PID
                list_result = await client.call_tool("list_processes", {})
                processes = json.loads(list_result[0].text)
                found_proc = next(
                    (
                        p
                        for p in processes
                        if p["command"] == pid_or_command and p["status"] == "running"
                    ),
                    None,
                )
                if not found_proc:
                    logger.error(
                        f"No running process found with command: '{pid_or_command}'"
                    )
                    sys.exit(1)
                pid_to_use = found_proc["pid"]

            # Now get the log paths
            paths_result = await client.call_tool(
                "get_process_log_paths", {"pid": pid_to_use}
            )
            paths = json.loads(paths_result[0].text)
            if "error" in paths:
                logger.error(f"Error getting log paths: {paths['error']}")
                sys.exit(1)

            for stream, path in paths.items():
                print(path)

    except Exception as e:
        logger.error(f"Failed to connect to persistproc server at {mcp_url}.")
        logger.debug(f"Connection error: {e}")
        sys.exit(1)


async def run_and_tail_async(args: argparse.Namespace):
    """
    Client-side function to start a process via the server and tail its logs.
    """
    if not args.command:
        logger.error("No command provided to run.")
        return

    command_str = " ".join(args.command)
    mcp_url = f"http://{args.host}:{args.port}/mcp/"

    client = Client(mcp_url)
    async with client:
        p_info = None
        # Capture the calling environment to ensure commands are found on the server
        call_env = dict(os.environ)

        # First, attempt to start the process
        logger.debug(f"Requesting to start command: '{command_str}'")
        start_result = await client.call_tool(
            "start_process",
            {
                "command": command_str,
                "working_directory": os.getcwd(),
                "environment": call_env,
            },
        )
        start_info = json.loads(start_result[0].text)

        # Check if it was already running
        if "error" in start_info and "is already running" in start_info["error"]:
            pid_match = re.search(r"PID (\d+)", start_info["error"])
            if not pid_match:
                logger.error(
                    f"Server error: Could not parse PID from error message: {start_info['error']}"
                )
                sys.exit(1)

            existing_pid = int(pid_match.group(1))

            if args.restart:
                logger.info(
                    f"Process '{command_str}' is running (PID {existing_pid}). Restarting as requested."
                )
                restart_result = await client.call_tool(
                    "restart_process", {"pid": existing_pid}
                )
                p_info = json.loads(restart_result[0].text)
            else:
                logger.info(
                    f"Process '{command_str}' is already running with PID {existing_pid}."
                )
                logger.info(
                    "Tailing existing logs. Use --restart to force a new process."
                )
                status_result = await client.call_tool(
                    "get_process_status", {"pid": existing_pid}
                )
                p_info = json.loads(status_result[0].text)

        # Check for other errors during start
        elif "error" in start_info:
            logger.error(f"Server returned an error on start: {start_info['error']}")
            sys.exit(1)

        # If no error, it's a fresh start
        else:
            logger.info(f"Starting process '{command_str}' for the first time.")
            p_info = start_info

        # Final check on the process info we ended up with
        if not p_info or "error" in p_info:
            logger.error(
                f"Failed to get a valid process state to monitor: {p_info.get('error', 'Unknown error')}"
            )
            sys.exit(1)

        pid = p_info.get("pid")
        if not pid:
            logger.error(f"Could not get PID from server response: {p_info}")
            sys.exit(1)

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

        # 3. Tail the log file, monitoring for restarts
        await tail_and_monitor_process_async(
            client, pid, command_str, combined_log_path, args, p_info
        )


POLL_INTERVAL = 1.0  # seconds


async def tail_and_monitor_process_async(
    client: Client,
    initial_pid: int,
    command_str: str,
    initial_log_path: Path,
    args: argparse.Namespace,
    initial_p_info: dict = None,
):
    """
    Tails a log file while monitoring the corresponding process for restarts and completion.
    """
    shutdown_event = asyncio.Event()

    def _process_line_for_raw_output(line: str) -> Optional[str]:
        if "[SYSTEM]" in line:
            return None
        return TIMESTAMP_REGEX.sub("", line, count=1)

    def _handle_sigint():
        # This handler will be called when SIGINT is received.
        print("\n--- Signal received, preparing to detach. ---", file=sys.stderr)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _handle_sigint)
    except NotImplementedError:
        pass  # Not supported on all platforms (e.g. Windows)

    current_pid = initial_pid
    current_log_path = initial_log_path
    last_known_start_time = (
        initial_p_info.get("start_time", "") if initial_p_info else ""
    )

    # This is the main loop that allows us to follow a process through restarts.
    while not shutdown_event.is_set():
        # Wait for the log file to appear, which can take a moment after a restart.
        wait_for_log_start = time.monotonic()
        while not current_log_path.exists():
            if time.monotonic() - wait_for_log_start > 5.0:
                logger.error(
                    f"Timed out waiting for log file {current_log_path} to appear."
                )
                return
            await asyncio.sleep(0.1)

        log_file = None
        try:
            log_file = current_log_path.open("r", encoding="utf-8")
        except FileNotFoundError:
            logger.error(
                f"Log file {current_log_path} not found after waiting. Aborting."
            )
            return

        print(
            f"--- Tailing output for PID {current_pid} ('{command_str}') ---",
            file=sys.stderr,
        )
        if current_pid != initial_pid:
            print(
                f"--- Process was restarted. Original PID was {initial_pid}. ---",
                file=sys.stderr,
            )

        stop_tail_event = threading.Event()

        def tail_worker(raw_log: bool):
            """The actual tailing logic that runs in a thread."""
            try:
                log_file.seek(0, 2)
                while not stop_tail_event.is_set():
                    line = log_file.readline()
                    if not line:
                        if stop_tail_event.is_set():
                            break
                        time.sleep(0.1)
                        continue

                    if raw_log:
                        output_line = line
                    else:
                        output_line = _process_line_for_raw_output(line)

                    if output_line is not None:
                        sys.stdout.write(output_line)
                        sys.stdout.flush()
            finally:
                if not log_file.closed:
                    log_file.close()
                logger.debug("Tail worker finished.")

        tail_thread = threading.Thread(
            target=tail_worker, args=(args.raw,), daemon=True
        )
        tail_thread.start()

        process_truly_exited = False
        restarted_proc = None

        # Main monitoring loop
        try:
            while tail_thread.is_alive() and not shutdown_event.is_set():
                try:
                    status_result = await client.call_tool(
                        "get_process_status", {"pid": current_pid}
                    )
                    p_status = json.loads(status_result[0].text)
                    if "error" in p_status or p_status.get("status") not in (
                        "running",
                        "starting",
                    ):
                        process_truly_exited = True
                        break  # Exit monitoring loop, process is gone.
                except Exception:
                    logger.warning("Could not get process status. Assuming it exited.")
                    process_truly_exited = True
                    break
                await asyncio.sleep(1.0)  # Polling interval

            if shutdown_event.is_set():
                # User-initiated shutdown
                break

            if process_truly_exited:
                list_res = await client.call_tool("list_processes", {})
                all_procs = json.loads(list_res[0].text)
                restarted_proc = find_restarted_process(
                    all_procs, command_str, last_known_start_time
                )

                if restarted_proc:
                    current_pid = restarted_proc["pid"]
                    last_known_start_time = restarted_proc["start_time"]
                    logs_result = await client.call_tool(
                        "get_process_log_paths", {"pid": current_pid}
                    )
                    log_paths = json.loads(logs_result[0].text)
                    current_log_path = Path(log_paths["combined"])
                    # Continue the outer `while` to start tailing the new process
                else:
                    logger.info("Process has exited and was not restarted.")
                    break  # Exit the outer `while` loop
        finally:
            # Cleanly stop the tailing thread
            stop_tail_event.set()
            tail_thread.join(timeout=2.0)

    # After the main loop, decide what to do on user-initiated exit
    if shutdown_event.is_set():
        logger.debug("Shutdown event received, deciding action.")
        should_stop = False
        if args.on_exit == "stop":
            should_stop = True
        elif args.on_exit == "detach":
            should_stop = False
        elif sys.stdin.isatty():
            try:
                stop_choice = input(
                    f"Stop running process '{command_str}' (PID {current_pid})? [y/N] "
                )
                if stop_choice.lower() == "y":
                    should_stop = True
            except (EOFError, KeyboardInterrupt):
                print()  # Print a newline to make output cleaner
                should_stop = False

        if should_stop:
            print(f"--- Stopping process {current_pid}... ---", file=sys.stderr)
            try:
                await client.call_tool("stop_process", {"pid": current_pid})
            except Exception as e:
                logger.error(f"Failed to stop process {current_pid}: {e}")
        else:
            print(
                "\n--- Detaching from log tailing. Process remains running. ---",
                file=sys.stderr,
            )

    # Cleanup signal handler
    try:
        loop.remove_signal_handler(signal.SIGINT)
    except NotImplementedError:
        pass


def find_restarted_process(
    processes: list, command_str: str, last_known_start_time: str
):
    """
    Given a list of processes, find one that looks like a restart of our target.
    A restarted process will have the same command string but a start_time
    that is newer than the last one we knew about.
    """
    for p in processes:
        if p.get("command") == command_str:
            # Check if the process is running and has a start time after the one we last saw.
            # This handles cases where multiple copies of the same command might exist.
            if (
                p.get("status") == "running"
                and p.get("start_time", "") > last_known_start_time
            ):
                return p
    return None


def run_client(args: argparse.Namespace):
    """Run the client-side CLI."""
    from .utils import setup_logging

    setup_logging(args.verbose)

    try:
        asyncio.run(run_and_tail_async(args))
    except KeyboardInterrupt:
        # Ensure graceful exit code (0) even if Ctrl+C is received very early,
        # before our inner async handlers have a chance to catch it. This
        # avoids negative return codes (-2) that cause CI test failures.
        print(
            "\n--- Detaching from log tailing. Process remains running. ---",
            file=sys.stderr,
        )
        sys.exit(0)
