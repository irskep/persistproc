from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _get_iso_ts() -> str:  # noqa: D401 – helper
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class LogManager:
    """Handle per-process log files & pump threads."""

    @dataclass(slots=True)
    class LogPaths:  # noqa: D401 – lightweight value object
        stdout: Path
        stderr: Path
        combined: Path

        # Make the instance behave *partly* like a mapping for legacy uses.
        def __getitem__(self, item: str) -> Path:  # noqa: D401 – mapping convenience
            return getattr(self, item)

        def __contains__(self, item: str) -> bool:  # noqa: D401 – mapping convenience
            return hasattr(self, item)

    def __init__(self, base_dir: Path):
        self._dir = base_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------
    # Public helpers
    # -------------------------------

    def paths_for(self, prefix: str) -> LogPaths:  # noqa: D401
        return self.LogPaths(
            stdout=self._dir / f"{prefix}.stdout",
            stderr=self._dir / f"{prefix}.stderr",
            combined=self._dir / f"{prefix}.combined",
        )

    def start_pumps(self, proc: subprocess.Popen, prefix: str) -> None:  # noqa: D401
        paths = self.paths_for(prefix)

        # open in text mode – we add timestamps manually
        stdout_fh = paths.stdout.open("a", encoding="utf-8")
        stderr_fh = paths.stderr.open("a", encoding="utf-8")
        comb_fh = paths.combined.open("a", encoding="utf-8")

        def _pump(src: subprocess.PIPE, primary, secondary) -> None:  # type: ignore[type-arg]
            # Blocking read; releases GIL.
            for b_line in iter(src.readline, b""):
                line = b_line.decode("utf-8", errors="replace")
                ts_line = f"{_get_iso_ts()} {line}"
                primary.write(ts_line)
                primary.flush()
                secondary.write(ts_line)
                secondary.flush()
            src.close()
            primary.close()

        threading.Thread(
            target=_pump, args=(proc.stdout, stdout_fh, comb_fh), daemon=True
        ).start()
        threading.Thread(
            target=_pump, args=(proc.stderr, stderr_fh, comb_fh), daemon=True
        ).start()

        def _close_combined() -> None:
            proc.wait()
            comb_fh.close()

        threading.Thread(target=_close_combined, daemon=True).start()
