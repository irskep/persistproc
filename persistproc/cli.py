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
                client, pid, command_str, combined_log_path, args.raw, p_info
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
    show_raw_log: bool = False,
    initial_p_info: dict = None,
):
    """
    Tails a log file while monitoring the corresponding process for restarts and completion.
    """
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
        print(f"--- Log file: {current_log_path} ---", file=sys.stderr)
        print("--- Press Ctrl+C to stop tailing. ---", file=sys.stderr)

        stop_event = threading.Event()
        tail_thread = None

        def _process_line_for_raw_output(line: str) -> Optional[str]:
            if "[SYSTEM]" in line:
                return None
            return TIMESTAMP_REGEX.sub("", line, count=1)

        def tail_worker(raw_log: bool):
            try:
                # Print existing content
                for line in log_file:
                    output_line = (
                        line if raw_log else _process_line_for_raw_output(line)
                    )
                    if output_line is not None:
                        sys.stdout.write(output_line)
                sys.stdout.flush()

                # Tail for new content
                while not stop_event.is_set():
                    line = log_file.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    output_line = (
                        line if raw_log else _process_line_for_raw_output(line)
                    )
                    if output_line is not None:
                        sys.stdout.write(output_line)
                        sys.stdout.flush()
            finally:
                log_file.close()

        tail_thread = threading.Thread(
            target=tail_worker, args=(show_raw_log,), daemon=True
        )
        tail_thread.start()

        restarted_info = None
        process_truly_exited = False

        try:
            # Monitor process status in the main async task
            while tail_thread.is_alive():
                try:
                    status_result = await client.call_tool(
                        "get_process_status", {"pid": current_pid}
                    )
                    p_status = json.loads(status_result[0].text)
                    if "error" in p_status or p_status.get("status") != "running":
                        # Process is not running. Check if it was restarted.
                        list_res = await client.call_tool("list_processes", {})
                        all_procs = json.loads(list_res[0].text)

                        # Find any other running process with the same command.
                        for p in all_procs:
                            if (
                                p.get("command") == command_str
                                and p.get("status") == "running"
                                and p.get("pid") != current_pid
                            ):
                                restarted_info = p
                                break

                        process_truly_exited = (
                            True  # Assume it's exited unless we find a restarted one
                        )
                        break  # Exit the inner monitoring loop

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Could not parse server status: {e}. Retrying.")
                except Exception as e:
                    logger.error(
                        f"Error monitoring process status: {e}. Assuming process exited."
                    )
                    process_truly_exited = True
                    break

                await asyncio.sleep(1.5)  # Polling interval

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n--- Log tailing interrupted. ---", file=sys.stderr)
            try:
                stop_choice = input(
                    f"Do you want to stop the running process '{command_str}' (PID {current_pid})? [y/N] "
                )
                if stop_choice.lower() == "y":
                    print(f"--- Stopping process {current_pid}... ---", file=sys.stderr)
                    await client.call_tool("stop_process", {"pid": current_pid})
            except (EOFError, KeyboardInterrupt):
                print(
                    "\n--- Detaching from log tailing. Process remains running. ---",
                    file=sys.stderr,
                )
            return  # Exit cleanly on interrupt

        finally:
            stop_event.set()
            if tail_thread:
                tail_thread.join(timeout=1.0)

        # --- End of inner monitoring block ---

        if restarted_info:
            print(
                f"\n--- Process '{command_str}' restarted. Now tracking new PID {restarted_info['pid']}. ---",
                file=sys.stderr,
            )
            try:
                new_pid = restarted_info["pid"]
                logs_res = await client.call_tool(
                    "get_process_log_paths", {"pid": new_pid}
                )
                log_paths = json.loads(logs_res[0].text)

                if "error" in log_paths:
                    logger.error(
                        f"Could not get log paths for restarted process: {log_paths['error']}"
                    )
                    break

                current_pid = new_pid
                current_log_path = Path(log_paths["combined"])
                last_known_start_time = restarted_info.get("start_time", "")
                # The 'while True' loop will now repeat with the new info
            except Exception as e:
                logger.error(f"Error switching to restarted process: {e}")
                break  # Exit the main loop on failure

        elif process_truly_exited:
            print(
                f"\n--- Process '{command_str}' (PID {current_pid}) has exited. ---",
                file=sys.stderr,
            )
            break  # Exit the main loop
        else:
            # This path is taken after a clean Ctrl+C that doesn't stop the process
            print(
                "\n--- Detaching from log tailing. Process remains running. ---",
                file=sys.stderr,
            )
            break


def run_client(args: argparse.Namespace):
    """Run the client-side CLI."""
    from .utils import setup_logging

    setup_logging(args.verbose)

    asyncio.run(run_and_tail_async(args))
