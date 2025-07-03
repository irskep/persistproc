from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

__all__ = [
    "run_cli",
    "start_persistproc",
    "extract_json",
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
    )

    # Wait for server readiness line.
    while True:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        if "Uvicorn running on" in line:
            break
    return proc


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
    raise ValueError("No JSON object found in text")
