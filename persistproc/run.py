from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

try:
    import termios
    import tty

    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

from persistproc.client import make_client
from persistproc.logging_utils import CLI_LOGGER

__all__ = ["run"]

logger = logging.getLogger(__name__)

# Regex to strip ISO-8601 timestamp prefix produced by ProcessManager
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_single_char() -> str | None:  # noqa: D401 – helper
    """Get a single character from stdin without waiting for Enter.

    Returns None if not a TTY, on Windows, or on error.
    Raises KeyboardInterrupt if Ctrl+C is pressed.
    """
    if not HAS_TERMIOS or not sys.stdin.isatty():
        return None

    try:
        # Save current terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Set terminal to raw mode
            tty.setraw(fd)
            char = sys.stdin.read(1)

            # Handle Ctrl+C (ASCII 3) in raw mode
            if ord(char) == 3:  # Ctrl+C
                raise KeyboardInterrupt

            return char
        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (OSError, termios.error):
        # Fall back to None if terminal manipulation fails
        return None


def _find_running_process_dict(
    processes: list[dict], cmd_tokens: list[str], working_directory: str
) -> dict | None:  # noqa: D401 – helper
    """Return the first *running* process dict matching *cmd_tokens*."""

    for info in processes:
        if (
            info.get("command") == cmd_tokens
            and info.get("status") == "running"
            and info.get("working_directory") == working_directory
        ):
            return info
    return None


def _resolve_combined_path(stdout_path: str) -> Path:  # noqa: D401 – helper
    """Given *stdout_path* as returned by *get_log_paths*, derive the *.combined* path."""

    if stdout_path.endswith(".stdout"):
        return Path(stdout_path[:-7] + ".combined")
    # Fallback – just append .combined alongside original name.
    return Path(stdout_path + ".combined")


def _tail_file(
    path: Path,
    stop_evt: threading.Event,
    raw: bool,
    buffer_mode: threading.Event | None = None,
    buffer: list[str] | None = None,
    buffer_lock: threading.Lock | None = None,
    from_beginning: bool = False,
) -> None:  # noqa: D401 – helper
    """Continuously print new lines appended to *path* until *stop_evt* is set.

    If *raw* is *False*, ISO timestamps are stripped and `[SYSTEM]` lines skipped.
    If *buffer_mode* is set, lines are appended to the buffer instead of printed.
    If *from_beginning* is *True*, start reading from the beginning of the file.
    """

    def _maybe_transform(line: str) -> str | None:  # noqa: D401 – helper
        if raw:
            return line
        if "[SYSTEM]" in line:
            return None
        return _TS_RE.sub("", line, count=1)

    try:
        with path.open("r", encoding="utf-8") as fh:
            if not from_beginning:
                fh.seek(0, os.SEEK_END)
            else:
                logger.debug("Starting tail from beginning of file %s", path)
            while not stop_evt.is_set():
                line = fh.readline()
                if line:
                    processed = _maybe_transform(line)
                    if processed is not None:
                        if (
                            buffer_mode is not None
                            and buffer_mode.is_set()
                            and buffer is not None
                            and buffer_lock is not None
                        ):
                            # Buffer mode - append to buffer instead of printing
                            with buffer_lock:
                                buffer.append(processed)
                        else:
                            # Normal mode - print directly
                            sys.stdout.write(processed)
                            sys.stdout.flush()
                else:
                    time.sleep(0.1)
    except FileNotFoundError:
        logger.error("Log file %s disappeared while tailing", path)
    except Exception as exc:  # pragma: no cover – safety net
        logger.exception("Unexpected error while tailing %s: %s", path, exc)


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------


async def _start_or_get_process_via_mcp(
    port: str,
    cmd_tokens: list[str],
    fresh: bool,
    working_directory: str,
    label: str | None = None,
) -> tuple[int, Path]:  # noqa: D401 – helper
    """Ensure the desired command is running via *persistproc* MCP.

    Returns ``(pid, combined_log_path)``.
    """

    command_str = " ".join(cmd_tokens)

    # The server process may still be starting up when tests launch the `run`
    # wrapper.  We therefore retry the whole *initialize → list* flow
    # for a short window, giving the server time to finish booting rather than
    # blocking forever on an open TCP connection that never sends headers.

    deadline = time.time() + 10.0  # seconds
    last_exc: Exception | None = None
    retry_count = 0

    while time.time() < deadline:
        retry_count += 1
        try:
            async with make_client(port) as client:
                # 1. Inspect existing processes.
                list_res = await client.call_tool("list", {})
                procs = json.loads(list_res[0].text).get("processes", [])

                existing = _find_running_process_dict(
                    procs, cmd_tokens, working_directory
                )

                if existing and fresh:
                    await client.call_tool(
                        "ctrl", {"action": "stop", "pid": existing["pid"]}
                    )
                    existing = None

                if existing is None:
                    start_params = {
                        "action": "start",
                        "command_or_label": command_str,
                        "working_directory": working_directory,
                        "environment": dict(os.environ),
                    }
                    if label is not None:
                        start_params["label"] = label
                    start_res = await client.call_tool("ctrl", start_params)
                    start_info = json.loads(start_res[0].text)
                    if start_info["error"]:
                        CLI_LOGGER.error(start_info["error"])
                        raise SystemExit(1)
                    pid = start_info["pid"]
                else:
                    pid = existing["pid"]

                # 2. Fetch log paths to locate the combined file.
                logs_res = await client.call_tool("list", {"pid": pid})
                logs_info = json.loads(logs_res[0].text)
                processes = logs_info.get("processes", [])
                if not processes:
                    raise RuntimeError(f"Process {pid} not found")

                stdout_path = processes[0]["log_stdout"]
                combined_path = _resolve_combined_path(stdout_path)

                return pid, combined_path
        except Exception as exc:  # pragma: no cover – retry window
            last_exc = exc
            # Only sleep if we have time left for another retry
            if time.time() + 0.25 < deadline:
                await asyncio.sleep(0.25)

    # All retries exhausted.
    exc_info = f" (last error: {last_exc})" if last_exc else ""
    raise RuntimeError(
        f"Unable to communicate with persistproc server on port {port} after {retry_count} attempts{exc_info}"
    )


async def _stop_process_via_mcp(port: int, pid: int) -> None:  # noqa: D401 – helper
    """Best-effort attempt to stop *pid* via MCP."""
    try:
        async with make_client(port) as client:
            await client.call_tool("ctrl", {"action": "stop", "pid": pid})
    except Exception as exc:  # pragma: no cover – soft failure
        logger.warning("Failed to stop process %s via MCP: %s", pid, exc)


# ---------------------------------------------------------------------------
# Additional MCP helpers for monitoring
# ---------------------------------------------------------------------------


async def _async_get_process_status(port: str, pid: int) -> str | None:  # noqa: D401
    """Return status string for *pid* or *None* if request fails."""

    async with make_client(port) as client:
        res = await client.call_tool("list", {"pid": pid})
        info = json.loads(res[0].text)
        processes = info.get("processes", [])
        if processes and len(processes) > 0:
            return processes[0].get("status")
        return None


async def _get_process_status(port: str, pid: int) -> str | None:  # noqa: D401
    try:
        result = await _async_get_process_status(port, pid)
        logger.debug("_get_process_status(pid=%s) -> %s", pid, result)
        return result
    except Exception as exc:  # pragma: no cover – swallow
        logger.warning("_get_process_status(pid=%s) failed: %s", pid, exc)
        return None


async def _async_find_restarted_process(
    port: str, cmd_tokens: list[str], working_directory: str, old_pid: int
) -> tuple[int | None, Path | None]:  # noqa: D401 – helper
    """If a new running process for *cmd_tokens* exists, return (pid, log_path)."""

    async with make_client(port) as client:
        list_res = await client.call_tool("list", {})
        procs = json.loads(list_res[0].text).get("processes", [])

        for proc in procs:
            if (
                proc.get("command") == cmd_tokens
                and proc.get("status") == "running"
                and proc.get("working_directory") == working_directory
                and proc.get("pid") != old_pid
            ):
                new_pid = proc["pid"]

                logs_res = await client.call_tool("list", {"pid": new_pid})
                logs_info = json.loads(logs_res[0].text)
                processes = logs_info.get("processes", [])
                if not processes:
                    continue  # Process not found, keep looking
                combined = _resolve_combined_path(processes[0]["log_stdout"])
                return new_pid, combined
    return None, None


async def _find_restarted_process(
    port: str, cmd_tokens: list[str], working_directory: str, old_pid: int
) -> tuple[int | None, Path | None]:  # noqa: D401
    try:
        return await _async_find_restarted_process(
            port, cmd_tokens, working_directory, old_pid
        )
    except Exception:  # pragma: no cover – swallow
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    command: str,
    args: Sequence[str],
    *,
    fresh: bool = False,
    on_exit: str = "ask",  # ask|stop|detach
    raw: bool = False,
    port: int | None = None,
    label: str | None = None,
) -> None:  # noqa: D401
    """Ensure *command* is running via *persistproc* and tail its combined output.

    Parameters
    ----------
    command
        Executable or program name to run.
    args
        Positional arguments passed to *command*.
    fresh
        If *True* and an instance of the target command is already running, stop
        it first before starting a new one.
    on_exit
        Behaviour when the user terminates the tailing session with *Ctrl+C*:

        * ``ask``   – interactively prompt whether to stop or detach (default).
        * ``stop``  – stop the managed process immediately.
        * ``detach`` – leave the process running.
    raw
        If *True*, raw log lines are printed without stripping ISO timestamps or
        skipping `[SYSTEM]` lines.
    port
        TCP port of the persistproc server.  If *None*, falls back to the
        ``PERSISTPROC_PORT`` environment variable (or 8947 if unset).
    """
    asyncio.run(
        _run(
            command, args, fresh=fresh, on_exit=on_exit, raw=raw, port=port, label=label
        )
    )


async def _run(
    command: str,
    args: Sequence[str],
    *,
    fresh: bool = False,
    on_exit: str = "ask",  # ask|stop|detach
    raw: bool = False,
    port: int | None = None,
    label: str | None = None,
) -> None:  # noqa: D401
    """Async implementation of run functionality."""
    cmd_tokens = [command, *args]
    cmd_str = " ".join(cmd_tokens)
    cwd = os.getcwd()

    # ------------------------------------------------------------------
    # Set up custom SIGINT handler using the event loop
    # ------------------------------------------------------------------

    shutdown_event = asyncio.Event()

    def handle_sigint():
        logger.debug("SIGINT received, setting shutdown event")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint)
    logger.debug("SIGINT handler installed via event loop")

    logger.debug("run(command=%s) starting", cmd_str)

    # ------------------------------------------------------------------
    # Prep connection details (host is always localhost for now).
    # ------------------------------------------------------------------

    try:
        pid, combined_path = await _start_or_get_process_via_mcp(
            port, cmd_tokens, fresh, cwd, label
        )
    except (ConnectionError, OSError) as exc:
        CLI_LOGGER.error(
            "Could not connect to persistproc server on port %s – is it running?", port
        )
        CLI_LOGGER.error("Start the server with: persistproc serve --port %s", port)
        logger.debug("Connection details: %s", exc)
        sys.exit(1)
    except Exception as exc:
        # Handle timeout exceptions and other connection issues
        exc_name = exc.__class__.__name__
        if "timeout" in exc_name.lower() or "timeout" in str(exc).lower():
            CLI_LOGGER.error(
                "Connection to persistproc server on port %s timed out – is it running?",
                port,
            )
            CLI_LOGGER.error("Start the server with: persistproc serve --port %s", port)
        elif "connection" in str(exc).lower():
            CLI_LOGGER.error(
                "Could not connect to persistproc server on port %s – is it running?",
                port,
            )
            CLI_LOGGER.error("Start the server with: persistproc serve --port %s", port)
        else:
            CLI_LOGGER.error("Failed to communicate with persistproc server: %s", exc)
        logger.debug("Full error details: %s", exc)
        sys.exit(1)

    logger.info(
        "Tailing combined output at %s (PID %s) – press Ctrl+C to detach",
        combined_path,
        pid,
    )

    # Ensure the combined log file exists before attempting to tail it.
    deadline = time.time() + 5.0  # seconds
    while not combined_path.exists() and time.time() < deadline:
        time.sleep(0.05)

    if not combined_path.exists():
        CLI_LOGGER.error("Combined log %s did not appear; aborting tail", combined_path)
        return

        # ------------------------------------------------------------------
    # Tail loop – runs in a thread so we can capture Ctrl+C cleanly.
    # ------------------------------------------------------------------
    stop_evt = threading.Event()
    buffer_mode = threading.Event()  # Controls when to buffer vs print

    # Buffer for capturing output during user prompt
    output_buffer: list[str] = []
    buffer_lock = threading.Lock()

    def _start_tail_thread(p: Path, from_beginning: bool = False):  # noqa: D401 – helper
        t = threading.Thread(
            target=_tail_file,
            args=(
                p,
                stop_evt,
                raw,
                buffer_mode,
                output_buffer,
                buffer_lock,
                from_beginning,
            ),
            daemon=True,
        )
        t.start()
        return t

    tail_thread = _start_tail_thread(combined_path)

    last_status_check = time.time()

    try:
        while True:
            # Check for shutdown signal
            if shutdown_event.is_set():
                logger.debug("Shutdown event detected, handling graceful exit")
                break

            # Use asyncio.sleep instead of blocking tail_thread.join
            await asyncio.sleep(0.3)
            logger.debug(
                "Main monitoring loop iteration, tail_thread.is_alive=%s",
                tail_thread.is_alive(),
            )

            # Periodically check process status.
            if time.time() - last_status_check >= 1.0:
                last_status_check = time.time()
                logger.debug("Performing periodic status check for PID %s", pid)
                try:
                    status_res = await _get_process_status(port, pid)
                    logger.debug("Status check result for PID %s: %s", pid, status_res)
                except Exception as exc:  # pragma: no cover – report but continue
                    logger.debug("Status poll failed: %s", exc)
                    status_res = None

                if status_res != "running":
                    logger.info(
                        "Process PID %s is no longer running (status=%s), looking for replacement",
                        pid,
                        status_res,
                    )
                    # Process exited – look for replacement.
                    new_pid, new_combined = await _find_restarted_process(
                        port, cmd_tokens, cwd, pid
                    )
                    if new_pid is None:
                        logger.info(
                            "No replacement process found, exiting monitoring loop"
                        )
                        break  # no restart – we're done

                    # Restart detected → switch tail.
                    logger.info(
                        "Process was restarted (old PID %s → new PID %s). Switching log tail.",
                        pid,
                        new_pid,
                    )

                    pid = new_pid
                    combined_path = new_combined

                    stop_evt.set()
                    tail_thread.join(timeout=1.0)

                    stop_evt.clear()
                    tail_thread = _start_tail_thread(combined_path, from_beginning=True)

            if not tail_thread.is_alive():
                # Tail finished naturally (e.g., log file closed) – exit loop.
                logger.info("Tail thread died, exiting monitoring loop")
                break
    finally:
        # Always clean up on exit
        stop_evt.set()
        tail_thread.join(timeout=1.0)

    # Handle shutdown signal if it was set
    if shutdown_event.is_set():
        logger.debug("Ctrl+C received – deciding action (on_exit=%s)", on_exit)

        # Start buffering output during the prompt
        output_buffer.clear()
        buffer_mode.set()  # Enable buffering mode

        def _should_stop() -> bool:
            if on_exit == "stop":
                return True
            if on_exit == "detach":
                return False
            # ask
            if not sys.stdin.isatty():
                # Non-interactive – default to detach.
                return False
            try:
                sys.stdout.write(
                    f"Stop running process '{cmd_str}' in '{cwd}' (PID {pid})? [y/N] "
                )
                sys.stdout.flush()

                # Try to get single character input
                char = _get_single_char()
                if char is not None:
                    # Print the character so user sees what they pressed
                    sys.stdout.write(char + "\n")
                    sys.stdout.flush()
                    return char.lower() == "y"
                else:
                    # Fall back to regular input() if single char doesn't work
                    reply = input()
                    return reply.strip().lower() == "y"
            except (EOFError, KeyboardInterrupt):
                # If user presses Ctrl+C during the prompt, default to detach
                sys.stdout.write("\n")  # Add newline for clean output
                return False

        if _should_stop():
            logger.info("User chose to stop process PID %s", pid)

            # Print any buffered output from during the prompt
            with buffer_lock:
                if output_buffer:
                    sys.stdout.write("".join(output_buffer))
                    sys.stdout.flush()
                    output_buffer.clear()

            # Disable buffering mode to resume normal printing
            buffer_mode.clear()

            # Send stop signal
            t0 = time.time()
            logger.debug("Sending stop signal to PID %s", pid)
            await _stop_process_via_mcp(port, pid)
            logger.debug("stop MCP request completed in %.3fs", time.time() - t0)

            # Monitor until process exits, continuing to tail output
            deadline = time.time() + 6.0  # <= monitor tick + grace
            last_status_check = time.time()
            logger.debug(
                "Starting shutdown monitoring loop for PID %s, deadline in %.1f seconds",
                pid,
                6.0,
            )

            while time.time() < deadline:
                # Use asyncio.sleep instead of blocking tail_thread.join
                await asyncio.sleep(0.3)
                time_left = deadline - time.time()
                logger.debug(
                    "Shutdown monitoring loop iteration, time_left=%.1f, tail_thread.is_alive=%s",
                    time_left,
                    tail_thread.is_alive(),
                )

                # Periodically check process status
                if time.time() - last_status_check >= 1.0:
                    last_status_check = time.time()
                    logger.debug("Performing shutdown status check for PID %s", pid)
                    try:
                        status_after = await _get_process_status(port, pid)
                        logger.debug("Status check during shutdown: %s", status_after)
                        if status_after != "running":
                            logger.info(
                                "Process PID %s stopped during shutdown monitoring",
                                pid,
                            )
                            break
                    except Exception as exc:  # pragma: no cover – report but continue
                        logger.debug("Status poll failed during shutdown: %s", exc)

                if not tail_thread.is_alive():
                    # Tail finished naturally (e.g., log file closed) – exit loop
                    logger.debug("Tail thread died during shutdown monitoring")
                    break

            # Give a brief moment for any final output to be captured
            logger.debug(
                "Shutdown monitoring complete, sleeping briefly for final output"
            )
            time.sleep(0.5)

            # Final cleanup
            logger.debug("Stopping tail thread and performing final cleanup")
            stop_evt.set()
            tail_thread.join(timeout=1.0)

            # Final status check for logging
            final_status = await _get_process_status(port, pid)
            logger.debug("Final status after stop wait: %s", final_status)

            # Exit immediately: cleanup done.
            logger.debug("Exiting after stop")
            return
        else:
            logger.info("User chose to detach – process PID %s left running", pid)

            # Clear buffer and resume normal tailing
            with buffer_lock:
                output_buffer.clear()

            # Disable buffering mode to resume normal printing
            buffer_mode.clear()

            # Continue with normal monitoring loop
            last_status_check = time.time()
            logger.debug("Resuming normal monitoring loop after detach choice")

            while True:
                # Use asyncio.sleep instead of blocking tail_thread.join
                await asyncio.sleep(0.3)
                logger.debug(
                    "Detach monitoring loop iteration, tail_thread.is_alive=%s",
                    tail_thread.is_alive(),
                )

                # Periodically check process status.
                if time.time() - last_status_check >= 1.0:
                    last_status_check = time.time()
                    logger.debug(
                        "Performing periodic status check for PID %s (detach mode)",
                        pid,
                    )
                    try:
                        status_res = await _get_process_status(port, pid)
                        logger.debug(
                            "Status check result for PID %s (detach mode): %s",
                            pid,
                            status_res,
                        )
                    except Exception as exc:  # pragma: no cover – report but continue
                        logger.debug("Status poll failed: %s", exc)
                        status_res = None

                    if status_res != "running":
                        logger.info(
                            "Process PID %s is no longer running (detach mode, status=%s), looking for replacement",
                            pid,
                            status_res,
                        )
                        # Process exited – look for replacement.
                        new_pid, new_combined = await _find_restarted_process(
                            port, cmd_tokens, cwd, pid
                        )
                        if new_pid is None:
                            logger.info(
                                "No replacement process found (detach mode), exiting monitoring loop"
                            )
                            break  # no restart – we're done

                        # Restart detected → switch tail.
                        logger.info(
                            "Process was restarted (old PID %s → new PID %s). Switching log tail.",
                            pid,
                            new_pid,
                        )

                        pid = new_pid
                        combined_path = new_combined

                        stop_evt.set()
                        tail_thread.join(timeout=1.0)

                        stop_evt.clear()
                        tail_thread = _start_tail_thread(
                            combined_path, from_beginning=True
                        )

                if not tail_thread.is_alive():
                    # Tail finished naturally (e.g., log file closed) – exit loop.
                    break

        # Exit immediately: cleanup done.
        return

    logger.debug("run(command=%s) finished", cmd_str)
