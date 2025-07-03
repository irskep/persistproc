import sys
from pathlib import Path
from typing import Iterable
import signal

import pytest

LOG_PATTERN = "persistproc.run.*.log"


def _find_latest_log(dirs: Iterable[Path]) -> Path | None:
    """Return the most recently modified log file among *dirs* (recursive)."""
    latest: Path | None = None
    for base in dirs:
        if not base.exists():
            continue
        for path in base.rglob(LOG_PATTERN):
            if latest is None or path.stat().st_mtime > latest.stat().st_mtime:
                latest = path
    return latest


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):  # noqa: D401 – pytest hook
    # Let pytest perform its normal processing first.
    outcome = yield
    rep = outcome.get_result()

    # Only act after the *call* phase and when the test has failed.
    if rep.when != "call" or rep.passed:
        return

    # Collect candidate directories to search.
    candidate_dirs: list[Path] = []

    # Common temporary directory fixtures.
    for fixture_name in ("tmp_path", "tmp_path_factory"):
        if fixture_name in item.funcargs:
            fixture_val = item.funcargs[fixture_name]
            if isinstance(fixture_val, Path):
                candidate_dirs.append(fixture_val)
            elif hasattr(fixture_val, "getbasetemp"):
                # tmp_path_factory
                candidate_dirs.append(Path(fixture_val.getbasetemp()))

    # Environment override allows tests to specify additional locations.
    extra_dir = item.config.getoption("--persistproc-data-dir", default=None)
    if extra_dir:
        candidate_dirs.append(Path(extra_dir))

    # Always include repository-level artifacts directory if present.
    repo_artifacts = Path(__file__).parent / "_artifacts"
    candidate_dirs.append(repo_artifacts)

    latest_log = _find_latest_log(candidate_dirs)

    if latest_log is None:
        rep.sections.append(("persistproc-log", "[no log file found]"))
        return

    try:
        contents = latest_log.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover – best-effort
        contents = f"<error reading log file {latest_log}: {exc}>"

    # Attach as an additional section so `-vv` shows it nicely; also write to
    # stderr immediately so it appears even with minimal verbosity.
    rep.sections.append(("persistproc-log", contents))
    sys.stderr.write("\n==== persistproc server log (latest) ====\n")
    sys.stderr.write(contents)
    sys.stderr.write("\n==== end of persistproc server log ====\n\n")


@pytest.fixture(autouse=True)
def _enforce_timeout(request):
    """Fail tests that run longer than the allowed time.

    Default timeout is 30 seconds unless a test is marked with
    ``@pytest.mark.timeout(N)`` specifying a custom limit.
    """

    marker = request.node.get_closest_marker("timeout")
    timeout = int(marker.args[0]) if marker and marker.args else 30

    # Skip if timeout is non-positive or SIGALRM unavailable (e.g. Windows).
    if timeout <= 0 or sys.platform.startswith("win"):
        yield
        return

    def _alarm_handler(signum, frame):  # noqa: D401 – signal handler
        pytest.fail(f"Test timed out after {timeout} seconds", pytrace=False)

    previous = signal.signal(signal.SIGALRM, _alarm_handler)  # type: ignore[arg-type]
    signal.alarm(timeout)

    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)  # type: ignore[arg-type]
