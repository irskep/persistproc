from pathlib import Path
from typing import Optional

import logging


logger = logging.getLogger(__name__)


class ProcessManager:
    data_dir: Optional[Path]

    def __init__(self):
        self.data_dir = None

    def bootstrap(self, data_dir: Path):
        self.data_dir = data_dir
        logger.debug("ProcessManager bootstrapped with data_dir=%s", data_dir)

    def start_process(
        self,
        command: str,
        working_directory: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        logger.info(
            "[stub] start_process cmd=%s cwd=%s env=%s",
            command,
            working_directory,
            environment,
        )

    def stop_process(self, pid: int) -> None:
        logger.info("[stub] stop_process pid=%s", pid)
