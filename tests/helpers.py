from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any
import signal
import os

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
    proc = subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

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


def kill_persistproc(proc: subprocess.Popen[str]) -> None:
    """Kill the persistproc server."""
    # call kill-persistproc tool
    result = run_cli("kill-persistproc")
    pid = extract_json(result.stdout)["pid"]
    # loop until given pid is no longer running
    while os.path.exists(f"/proc/{pid}"):
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
    return subprocess.Popen(
        cli_cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def stop_run(proc: subprocess.Popen[str], timeout: float = 60.0) -> None:
    """Stop a subprocess by sending SIGINT and waiting up to timeout seconds."""
    if proc.poll() is not None:
        return

    # Send SIGINT and wait for process to stop
    proc.send_signal(signal.SIGINT)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
