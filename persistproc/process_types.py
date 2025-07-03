from __future__ import annotations

"""Shared dataclasses used by *persistproc* components.

Having these types in a dedicated module avoids circular imports between
``process_manager`` and ``tools``.
"""

from dataclasses import dataclass
from typing import List

__all__ = [
    "StartProcessResult",
    "StopProcessResult",
    "ProcessInfo",
    "ListProcessesResult",
    "ProcessStatusResult",
    "ProcessOutputResult",
    "ProcessLogPathsResult",
    "RestartProcessResult",
]


@dataclass
class StartProcessResult:
    pid: int


@dataclass
class StopProcessResult:
    """Result of a stop_process call.

    * ``exit_code`` is ``None`` when the target process could not be
    terminated (e.g. after SIGKILL timeout).  ``error`` then contains a short
    reason string suitable for logging or displaying to a user.
    """

    exit_code: int | None = None
    error: str | None = None


@dataclass
class ProcessInfo:
    pid: int
    command: List[str]
    working_directory: str
    status: str


@dataclass
class ListProcessesResult:
    processes: List[ProcessInfo]


@dataclass
class ProcessStatusResult:
    pid: int
    command: List[str]
    working_directory: str
    status: str


@dataclass
class ProcessOutputResult:
    output: List[str]


@dataclass
class ProcessLogPathsResult:
    stdout: str
    stderr: str


@dataclass
class RestartProcessResult:
    """Outcome of a restart operation.

    Either *pid* is set (success) or *error* is populated.
    """

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
