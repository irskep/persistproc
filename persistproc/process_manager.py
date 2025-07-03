from __future__ import annotations

# Minimal stubbed ProcessManager – no real process handling yet.

import logging
from pathlib import Path
from typing import Optional

from persistproc.process_types import (
    ListProcessesResult,
    ProcessInfo,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    StartProcessResult,
    StopProcessResult,
)


logger = logging.getLogger(__name__)


class ProcessManager:  # noqa: D101 – stub class
    def __init__(self) -> None:  # noqa: D401
        self.data_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self, data_dir: Path) -> None:  # noqa: D401
        self.data_dir = data_dir
        logger.debug("ProcessManager bootstrapped with data_dir=%s", data_dir)

    # ------------------------------------------------------------------
    # Stubbed API – returns placeholders only
    # ------------------------------------------------------------------

    def start_process(
        self,
        command: str,
        working_directory: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> StartProcessResult:  # noqa: D401
        logger.info("[stub] start_process cmd=%s", command)
        return StartProcessResult(pid=0)

    def list_processes(self) -> ListProcessesResult:  # noqa: D401
        logger.debug("[stub] list_processes")
        return ListProcessesResult(processes=[])

    def get_process_status(self, pid: int) -> ProcessStatusResult:  # noqa: D401
        logger.debug("[stub] get_process_status pid=%s", pid)
        return ProcessStatusResult(
            pid=pid, command=[], working_directory="", status="unknown"
        )

    def stop_process(
        self, pid: int, force: bool = False
    ) -> StopProcessResult:  # noqa: D401
        logger.info("[stub] stop_process pid=%s force=%s", pid, force)
        return StopProcessResult(exit_code=0)

    def restart_process(self, pid: int) -> None:  # noqa: D401
        logger.info("[stub] restart_process pid=%s", pid)

    def get_process_output(
        self,
        pid: int,
        stream: str,
        lines: Optional[int] = None,
    ) -> ProcessOutputResult:  # noqa: D401
        logger.debug("[stub] get_process_output pid=%s stream=%s", pid, stream)
        return ProcessOutputResult(output=[])

    def get_process_log_paths(self, pid: int) -> ProcessLogPathsResult:  # noqa: D401
        logger.debug("[stub] get_process_log_paths pid=%s", pid)
        return ProcessLogPathsResult(stdout="", stderr="")
