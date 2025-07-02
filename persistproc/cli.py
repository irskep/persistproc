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

from fastmcp.client import Client

logger = logging.getLogger("persistproc")

# Constants for log processing
TIMESTAMP_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PersistProc: Manage and monitor long-running processes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the MCP server in the background
  persistproc --serve &

  # Run a command and tail its output (raw script output is the default).
  persistproc sleep 30

  # To view the full, timestamped log file output:
  persistproc --raw sleep 30

  # Run a command with arguments
  persistproc python -m http.server
""",
    )
    parser.add_argument(
        "--serve", action="store_true", help="Run the PersistProc MCP server."
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the process if it's already running.",
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
        "--raw",
        action="store_true",
        help="Display the raw, timestamped log file content instead of the clean process output.",
    )
    parser.add_argument(
        "--on-exit",
        choices=["stop", "detach"],
        default=None,
        help="What to do when Ctrl+C is pressed. 'stop' will stop the process, 'detach' will leave it running. If not provided, you will be prompted.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run and monitor.",
    )
    return parser, parser.parse_args()


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
                logger.error(
                    f"Server returned an error on start: {start_info['error']}"
                )
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

    except Exception as e:
        logger.error(
            f"Failed to connect to persistproc server at {mcp_url}. Is it running with '--serve'?"
        )
        logger.debug(f"Connection details: {e}")
        sys.exit(1)


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
        # This will be raised on systems that don't support add_signal_handler (e.g., Windows)
        # We can ignore it for this project as it's Unix-only.
        pass

    current_pid = initial_pid
    current_log_path = initial_log_path
    last_known_start_time = (
        initial_p_info.get("start_time", "") if initial_p_info else ""
    )

    # This is the main loop that allows us to follow a process through restarts.
    while True:
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

        def is_process_alive():
            """Synchronous helper to check process status from the thread."""
            try:
                # This is a blocking call from a worker thread to the main event loop
                future = asyncio.run_coroutine_threadsafe(
                    client.call_tool("get_process_status", {"pid": current_pid}), loop
                )
                status_result = future.result(timeout=2.0)
                p_status = json.loads(status_result[0].text)
                return "error" not in p_status and p_status.get("status") in (
                    "running",
                    "starting",
                )
            except Exception:
                return False

        def tail_worker(raw_log: bool):
            """The actual tailing logic that runs in a thread."""
            nonlocal last_known_start_time
            try:
                log_file.seek(0, 2)  # Seek to the end to only show new lines
                while not shutdown_event.is_set():
                    try:
                        line = log_file.readline()
                    except ValueError:
                        # This happens when the main thread closes the file
                        # to unblock us during shutdown.
                        break

                    if not line:
                        # Check if process is still alive before sleeping
                        if shutdown_event.is_set() or not is_process_alive():
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

        # Monitor the thread's liveness and the shutdown event
        while tail_thread.is_alive():
            if shutdown_event.is_set():
                break
            await asyncio.sleep(0.2)

        # If we are shutting down, unblock the thread by closing its file.
        if shutdown_event.is_set():
            if log_file and not log_file.closed:
                log_file.close()

        # Wait for the tailing thread to finish its cleanup
        tail_thread.join(timeout=1.0)

        # If the event was set, we are done, so exit the restart loop.
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
            break

        # Check if the process is still alive. If not, see if it was restarted.
        try:
            status_result = await client.call_tool(
                "get_process_status", {"pid": current_pid}
            )
            p_status = json.loads(status_result[0].text)
            if "error" not in p_status and p_status.get("status") in (
                "running",
                "starting",
            ):
                # Process is still alive but tailer exited. This shouldn't happen.
                logger.warning("Tailing ended but process is still running. Detaching.")
                break
        except Exception:
            # Cannot get status, assume it's gone.
            pass

        # Process is not running. Check if it was restarted.
        try:
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
                continue  # Loop to start tailing the new process
            else:
                logger.info("Process has exited and was not restarted.")
                break  # Exit the while loop
        except Exception as e:
            logger.error(f"Failed to check for restarted process: {e}")
            break

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
