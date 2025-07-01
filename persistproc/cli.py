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

  # Run a command with quotes and tail its output
  persistproc "python -m http.server"
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

            # 3. Tail the log file
            await tail_and_monitor_process_async(
                client, pid, command_str, combined_log_path, args.raw
            )

    except Exception as e:
        logger.error(
            f"Failed to connect to persistproc server at {mcp_url}. Is it running with '--serve'?"
        )
        logger.debug(f"Connection details: {e}")
        sys.exit(1)


async def tail_and_monitor_process_async(
    client: Client,
    pid: int,
    command_str: str,
    log_path: Path,
    show_raw_log: bool = False,
):
    """Tails a log file while monitoring the corresponding process for completion."""
    while not log_path.exists():
        await asyncio.sleep(0.1)

    log_file = log_path.open("r")

    print(f"--- Tailing output for PID {pid} ('{command_str}') ---", file=sys.stderr)
    print(f"--- Log file: {log_path} ---", file=sys.stderr)
    print("--- Press Ctrl+C to stop tailing. ---", file=sys.stderr)

    stop_event = threading.Event()

    def _process_line_for_raw_output(line: str) -> Optional[str]:
        if "[SYSTEM]" in line:
            return None  # Suppress system logs in raw mode

        # Use re.sub to remove only the prefix, which is cleaner than
        # managing capture groups that might eat the trailing newline.
        return TIMESTAMP_REGEX.sub("", line, count=1)

    def tail_worker(raw_log: bool):
        # First, print any existing content in the file
        for line in log_file:
            output_line = line if raw_log else _process_line_for_raw_output(line)
            if output_line is not None:
                sys.stdout.write(output_line)
        sys.stdout.flush()

        # Now, tail for new content
        while not stop_event.is_set():
            line = log_file.readline()
            if not line:
                time.sleep(0.1)  # Avoid busy-waiting
                continue

            output_line = line if raw_log else _process_line_for_raw_output(line)
            if output_line is not None:
                sys.stdout.write(output_line)
                sys.stdout.flush()
        log_file.close()

    tail_thread = threading.Thread(
        target=tail_worker, args=(show_raw_log,), daemon=True
    )
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
                    status = p_status.get("status", "unknown")
                    exit_code = p_status.get("exit_code")
                    message = f"Process {pid} is no longer running (status: {status}"
                    if exit_code is not None:
                        message += f", exit_code: {exit_code}"
                    message += ")."
                    logger.info(message)
                    break
            except Exception as e:
                logger.debug(f"Could not poll process status: {e}")
                break  # Stop if we can't talk to the server

            await asyncio.sleep(2)

    except (KeyboardInterrupt, asyncio.CancelledError):
        stop_event.set()  # Stop the tailing thread immediately
        print("\n--- Log tailing interrupted. ---", file=sys.stderr)
        try:
            choice = ""
            # Platform-specific single-character input for Unix-like systems
            if sys.platform != "win32":
                import tty, termios

                print(
                    f"Do you want to stop the running process '{command_str}' (PID {pid})? [y/N] ",
                    end="",
                    flush=True,
                )
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(sys.stdin.fileno())
                    choice = sys.stdin.read(1).lower()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                print(choice)  # Echo the choice to the user for clarity
            else:
                # Standard input fallback for Windows
                choice = (
                    input(
                        f"Do you want to stop the running process '{command_str}' (PID {pid})? [y/N] "
                    )
                    .lower()
                    .strip()
                )

            if choice == "y":
                print(f"--- Sending stop request for PID {pid}... ---", file=sys.stderr)
                # We can still await here because asyncio.run waits for the cancelled task to finish.
                stop_result = await client.call_tool(
                    "stop_process", {"pid": pid, "force": False}
                )
                stop_info = json.loads(stop_result[0].text)
                if "error" in stop_info:
                    logger.error(
                        f"Failed to stop process: {stop_info['error']}", file=sys.stderr
                    )
                else:
                    print("--- Stop request sent successfully. ---", file=sys.stderr)
            else:
                print(
                    f"--- Leaving process PID {pid} running in the background. ---",
                    file=sys.stderr,
                )
        except KeyboardInterrupt:
            # This handles Ctrl+C being pressed during the input() prompt
            print("\n--- Prompt aborted. Leaving process running. ---", file=sys.stderr)
        except Exception as e:
            logger.error(
                f"Could not communicate with server to stop process {pid}: {e}",
                file=sys.stderr,
            )

    finally:
        stop_event.set()
        tail_thread.join(timeout=2)


def run_client(args: argparse.Namespace):
    """Run the client-side CLI."""
    from .utils import setup_logging

    setup_logging(args.verbose)

    asyncio.run(run_and_tail_async(args))
