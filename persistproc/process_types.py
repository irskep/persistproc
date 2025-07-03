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
