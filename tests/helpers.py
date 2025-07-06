from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

__all__ = [
    "run_cli",
    "start_persistproc",
    "extract_json",
    "start_run",
    "stop_run",
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the persistproc CLI synchronously and capture output."""
    cmd = ["python", "-m", "persistproc", "-vv", *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def start_persistproc() -> subprocess.Popen[str]:
    """Start persistproc server in the background and wait until ready."""
    cmd = ["python", "-m", "persistproc", "-vv", "serve"]

    # Cross-platform process creation
    kwargs = {
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }

    if os.name == "nt":
        # Windows: Use CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # Unix-like: Use start_new_session
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    # Wait for server readiness line.
    while True:
        line = proc.stdout.readline()
        if not line:
            # log the line so tests can see it
            time.sleep(0.05)
            continue
        if "Uvicorn running on" in line:
            # log the line so tests can see it
            print(line)
            time.sleep(1)
            break
    return proc


def _is_process_running(pid: int) -> bool:
    """Check if process is running cross-platform."""
    try:
        if os.name == "nt":
            # Windows: Use tasklist command
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in result.stdout
        else:
            # Unix-like: Use os.kill with signal 0
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def kill_persistproc(proc: subprocess.Popen[str]) -> None:
    """Kill the persistproc server."""
    # call kill-persistproc tool
    result = run_cli("kill-persistproc")
    pid = extract_json(result.stdout)["pid"]
    # loop until given pid is no longer running
    while _is_process_running(pid):
        time.sleep(0.1)


def extract_json(text: str) -> Any:
    """Return the last JSON object found in *text* (stderr/stdout)."""
    end = None
    depth = 0
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if ch == "}":
            if depth == 0:
                end = i
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0 and end is not None:
                try:
                    return json.loads(text[i : end + 1])
                except json.JSONDecodeError:
                    depth = 0
                    end = None
    raise ValueError("No JSON object found in text: " + text)


def start_run(cmd_tokens: list[str], *, on_exit: str = "stop") -> subprocess.Popen[str]:
    """Start `persistproc run …` in a background process.

    Returns the *Popen* instance so callers can terminate it with SIGINT.
    """

    cli_cmd = [
        "python",
        "-m",
        "persistproc",
        "-vv",
        "run",
        "--on-exit",
        on_exit,
        "--",
        *cmd_tokens,
    ]

    # Cross-platform process creation
    kwargs = {
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }

    if os.name == "nt":
        # Windows: Use CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # Unix-like: Use start_new_session
        kwargs["start_new_session"] = True

    return subprocess.Popen(cli_cmd, **kwargs)


def stop_run(proc: subprocess.Popen[str], timeout: float = 15.0) -> None:
    """Stop a subprocess by sending SIGINT and waiting up to timeout seconds."""
    if proc.poll() is not None:
        return

    # Send interrupt signal cross-platform
    try:
        if os.name == "nt":
            # Windows: Use CTRL_C_EVENT, but fallback to terminate if that fails
            try:
                proc.send_signal(signal.CTRL_C_EVENT)
            except (OSError, AttributeError):
                # CTRL_C_EVENT may not work in all contexts, fallback to terminate
                proc.terminate()
        else:
            # Unix-like: Use SIGINT
            proc.send_signal(signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        # Process may have already exited
        pass

    try:
        # Wait for the process to terminate. The `run` command's own logic
        # can take several seconds to complete, especially when stopping a
        # child process, so we need a generous timeout here to avoid killing
        # it prematurely, which was the source of test flakes.
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # If it's still alive, force-kill it.
        print(f"Process {proc.pid} did not exit after {timeout}s, killing.")
        try:
            if os.name == "nt":
                # Windows: Use terminate then kill
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            else:
                # Unix-like: Use process group kill
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError):
            proc.kill()  # Fallback
        finally:
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass  # Process may already be dead
