from __future__ import annotations

import os
import sys
import time
import threading
import logging
from pathlib import Path
from typing import Sequence, Optional
import asyncio
import json
import re

from fastmcp.client import Client

# NOTE: We **import at runtime** inside functions to avoid circular imports with
# ``persistproc.cli``.  CLI initialises the singleton *ProcessManager* instance
# and bootstraps it **before** calling :pyfunc:`run`.

__all__ = ["run"]

logger = logging.getLogger(__name__)

# Regex to strip ISO-8601 timestamp prefix produced by ProcessManager
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_running_process_dict(
    processes: list[dict], cmd_tokens: list[str]
) -> Optional[dict]:  # noqa: D401 – helper
    """Return the first *running* process dict matching *cmd_tokens*."""

    for info in processes:
        if info.get("command") == cmd_tokens and info.get("status") == "running":
            return info
    return None


def _resolve_combined_path(stdout_path: str) -> Path:  # noqa: D401 – helper
    """Given *stdout_path* as returned by *get_process_log_paths*, derive the *.combined* path."""

    if stdout_path.endswith(".stdout"):
        return Path(stdout_path[:-7] + ".combined")
    # Fallback – just append .combined alongside original name.
    return Path(stdout_path + ".combined")


def _tail_file(
    path: Path, stop_evt: threading.Event, raw: bool
) -> None:  # noqa: D401 – helper
    """Continuously print new lines appended to *path* until *stop_evt* is set.

    If *raw* is *False*, ISO timestamps are stripped and `[SYSTEM]` lines skipped.
    """

    def _maybe_transform(line: str) -> str | None:  # noqa: D401 – helper
        if raw:
            return line
        if "[SYSTEM]" in line:
            return None
        return _TS_RE.sub("", line, count=1)

    try:
        with path.open("r", encoding="utf-8") as fh:
            fh.seek(0, os.SEEK_END)
            while not stop_evt.is_set():
                line = fh.readline()
                if line:
                    processed = _maybe_transform(line)
                    if processed is not None:
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
    mcp_url: str, cmd_tokens: list[str], fresh: bool
) -> tuple[int, Path]:  # noqa: D401 – helper
    """Ensure the desired command is running via *persistproc* MCP.

    Returns ``(pid, combined_log_path)``.
    """

    command_str = " ".join(cmd_tokens)

    async with Client(mcp_url) as client:
        # 1. Inspect existing processes.
        list_res = await client.call_tool("list_processes", {})
        procs = json.loads(list_res[0].text).get("processes", [])

        existing = _find_running_process_dict(procs, cmd_tokens)

        if existing and fresh:
            await client.call_tool("stop_process", {"pid": existing["pid"]})
            existing = None

        if existing is None:
            start_res = await client.call_tool(
                "start_process",
                {
                    "command": command_str,
                    "working_directory": os.getcwd(),
                    "environment": dict(os.environ),
                },
            )
            start_info = json.loads(start_res[0].text)
            if start_info.get("error"):
                raise RuntimeError(start_info["error"])
            pid = start_info["pid"]
        else:
            pid = existing["pid"]

        # 2. Fetch log paths to locate the combined file.
        logs_res = await client.call_tool("get_process_log_paths", {"pid": pid})
        logs_info = json.loads(logs_res[0].text)
        if logs_info.get("error"):
            raise RuntimeError(logs_info["error"])

        stdout_path = logs_info["stdout"]
        combined_path = _resolve_combined_path(stdout_path)

        return pid, combined_path


def _stop_process_via_mcp(mcp_url: str, pid: int) -> None:  # noqa: D401 – helper
    """Best-effort attempt to stop *pid* via MCP (synchronous wrapper)."""

    async def _do_stop() -> None:  # noqa: D401 – inner helper
        async with Client(mcp_url) as client:
            await client.call_tool("stop_process", {"pid": pid})

    try:
        asyncio.run(_do_stop())
    except Exception as exc:  # pragma: no cover – soft failure
        logger.warning("Failed to stop process %s via MCP: %s", pid, exc)


# ---------------------------------------------------------------------------
# Additional MCP helpers for monitoring
# ---------------------------------------------------------------------------


async def _async_get_process_status(mcp_url: str, pid: int) -> str | None:  # noqa: D401
    """Return status string for *pid* or *None* if request fails."""

    async with Client(mcp_url) as client:
        res = await client.call_tool("get_process_status", {"pid": pid})
        info = json.loads(res[0].text)
        return info.get("status")


def _get_process_status(
    mcp_url: str, pid: int
) -> str | None:  # noqa: D401 – sync shell
    try:
        return asyncio.run(_async_get_process_status(mcp_url, pid))
    except Exception:  # pragma: no cover – swallow
        return None


async def _async_find_restarted_process(
    mcp_url: str, cmd_tokens: list[str], old_pid: int
) -> tuple[int | None, Path | None]:  # noqa: D401 – helper
    """If a new running process for *cmd_tokens* exists, return (pid, log_path)."""

    async with Client(mcp_url) as client:
        list_res = await client.call_tool("list_processes", {})
        procs = json.loads(list_res[0].text).get("processes", [])

        for proc in procs:
            if (
                proc.get("command") == cmd_tokens
                and proc.get("status") == "running"
                and proc.get("pid") != old_pid
            ):
                new_pid = proc["pid"]

                logs_res = await client.call_tool(
                    "get_process_log_paths", {"pid": new_pid}
                )
                logs_info = json.loads(logs_res[0].text)
                combined = _resolve_combined_path(logs_info["stdout"])
                return new_pid, combined
    return None, None


def _find_restarted_process(
    mcp_url: str, cmd_tokens: list[str], old_pid: int
) -> tuple[int | None, Path | None]:  # noqa: D401
    try:
        return asyncio.run(_async_find_restarted_process(mcp_url, cmd_tokens, old_pid))
    except Exception:  # pragma: no cover – swallow
        return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    command: str,
    args: Sequence[str],
    verbose: int = 0,
    *,
    fresh: bool = False,
    on_exit: str = "ask",  # ask|stop|detach
    raw: bool = False,
) -> None:  # noqa: D401
    """Ensure *command* is running via *persistproc* and tail its combined output.

    Parameters
    ----------
    command
        Executable or program name to run.
    args
        Positional arguments passed to *command*.
    verbose
        Forwarded for parity with other sub-commands (currently unused).
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
    """

    cmd_tokens = [command, *args]
    cmd_str = " ".join(cmd_tokens)

    logger.debug("run(command=%s) starting", cmd_str)

    # ------------------------------------------------------------------
    # Prep connection details (host is always localhost for now).
    # ------------------------------------------------------------------
    port = int(os.environ.get("PERSISTPROC_PORT", "8947"))
    mcp_url = f"http://127.0.0.1:{port}/mcp/"

    try:
        pid, combined_path = asyncio.run(
            _start_or_get_process_via_mcp(mcp_url, cmd_tokens, fresh)
        )
    except ConnectionError as exc:
        logger.error(
            "Could not connect to persistproc server at %s – is it running?", mcp_url
        )
        logger.debug("Connection details: %s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        logger.error(str(exc))
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
        logger.error("Combined log %s did not appear; aborting tail", combined_path)
        return

    # ------------------------------------------------------------------
    # Tail loop – runs in a thread so we can capture Ctrl+C cleanly.
    # ------------------------------------------------------------------
    stop_evt = threading.Event()

    def _start_tail_thread(p: Path):  # noqa: D401 – helper
        t = threading.Thread(target=_tail_file, args=(p, stop_evt, raw), daemon=True)
        t.start()
        return t

    tail_thread = _start_tail_thread(combined_path)

    last_status_check = time.time()

    try:
        while True:
            tail_thread.join(timeout=0.3)

            # Periodically check process status.
            if time.time() - last_status_check >= 1.0:
                last_status_check = time.time()
                try:
                    status_res = asyncio.run(_get_process_status(mcp_url, pid))
                except Exception as exc:  # pragma: no cover – report but continue
                    logger.debug("Status poll failed: %s", exc)
                    status_res = None

                if status_res != "running":
                    # Process exited – look for replacement.
                    new_pid, new_combined = asyncio.run(
                        _find_restarted_process(mcp_url, cmd_tokens, pid)
                    )
                    if new_pid is None:
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
                    tail_thread = _start_tail_thread(combined_path)

            if not tail_thread.is_alive():
                # Tail finished naturally (e.g., log file closed) – exit loop.
                break
    except KeyboardInterrupt:
        # User pressed Ctrl+C – stop tailing first.
        stop_evt.set()
        tail_thread.join(timeout=2.0)

        logger.debug("Ctrl+C received – deciding action (on_exit=%s)", on_exit)

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
                reply = input(f"Stop running process '{cmd_str}' (PID {pid})? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                return False
            return reply.strip().lower() == "y"

        if _should_stop():
            logger.info("Stopping process PID %s", pid)
            _stop_process_via_mcp(mcp_url, pid)
        else:
            logger.info("Detaching – process PID %s left running", pid)

    finally:
        stop_evt.set()
        tail_thread.join(timeout=1.0)

    logger.debug("run(command=%s) finished", cmd_str)
