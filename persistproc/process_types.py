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
]


@dataclass
class StartProcessResult:
    pid: int


@dataclass
class StopProcessResult:
    exit_code: int


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
