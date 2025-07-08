from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "StartProcessResult",
    "StopProcessResult",
    "ProcessInfo",
    "ShutdownResult",
    "ListProcessesResult",
    "ProcessOutputResult",
    "RestartProcessResult",
    "ProcessControlResult",
    "StreamEnum",
]


class StreamEnum(str, Enum):
    stdout = "stdout"
    stderr = "stderr"
    combined = "combined"


@dataclass
class StartProcessResult:
    pid: int | None = None
    log_stdout: str | None = None
    log_stderr: str | None = None
    log_combined: str | None = None
    label: str | None = None
    error: str | None = None


@dataclass
class StopProcessResult:
    """Result of a stop call.

    * ``exit_code`` is ``None`` when the target process could not be
    terminated (e.g. after SIGKILL timeout).  ``error`` then contains a short
    reason string suitable for logging or displaying to a user.
    """

    exit_code: int | None = None
    error: str | None = None


@dataclass
class ProcessInfo:
    pid: int
    command: list[str]
    working_directory: str
    status: str
    label: str
    start_time: str | None = None
    end_time: str | None = None
    log_stdout: str | None = None
    log_stderr: str | None = None
    log_combined: str | None = None


@dataclass
class ListProcessesResult:
    processes: list[ProcessInfo]


@dataclass
class ProcessOutputResult:
    output: list[str] | None = None
    lines_before: int | None = None
    lines_after: int | None = None
    error: str | None = None


@dataclass
class RestartProcessResult:
    """Outcome of a restart operation.

    Either *pid* is set (success) or *error* is populated.
    """

    pid: int | None = None
    error: str | None = None


@dataclass
class ProcessControlResult:
    """Unified result for start, stop, and restart operations."""

    action: str  # "start", "stop", or "restart"
    pid: int | None = None  # new PID for start/restart
    exit_code: int | None = None  # exit code of stopped process for stop/restart
    log_stdout: str | None = None  # always included when available
    log_stderr: str | None = None  # always included when available
    log_combined: str | None = None  # always included when available
    label: str | None = None  # always included when available
    error: str | None = None


@dataclass
class ShutdownResult:
    pid: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Make dataclass types globally visible for Pydantic/fastmcp.
# ---------------------------------------------------------------------------
# *fastmcp* relies on Pydantic to introspect function signatures.  When a type
# annotation is expressed as a **string forward reference** (which can happen
# when code mutates ``__annotations__`` at runtime or when evaluating across
# module boundaries), Pydantic resolves that string by looking it up via
# ``eval`` against a globals dict which ultimately falls back to the interpreter
# built-ins namespace.
#
# To make sure *all* ``persistproc.process_types`` classes can always be found
# – regardless of the caller's module globals – we export them to
# ``builtins``.  This is a tiny, contained API surface so the risk of name
# collisions is negligible and the convenience for dynamic inspection
# libraries is significant.
#
# If additional result types are added in the future, simply append the class
# name to ``__all__`` and it will be exported automatically.

import builtins as _builtins  # noqa: E402 – after dataclass definitions

for _name in __all__:
    _builtins.__dict__.setdefault(_name, globals()[_name])
