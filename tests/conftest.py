import logging
import os
import random
import signal
import socket
import sys
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pytest

from tests.helpers import start_persistproc, stop_run

LOG_PATTERN = "persistproc.run.*.log"

ENV_PORT = "PERSISTPROC_PORT"
ENV_DATA_DIR = "PERSISTPROC_DATA_DIR"


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


@pytest.fixture(autouse=True)
def _persistproc_env(monkeypatch):
    """Configure default data dir and port for *persistproc* CLI/tests.

    This eliminates the need for per-test boilerplate – the CLI picks up these
    settings via environment variables automatically.
    """

    # ------------------------------------------------------------------
    # Data directory – keep within repository under *tests/_artifacts* so
    # developers can inspect logs easily.  Ensure uniqueness to avoid clashes
    # between concurrent/parameterised tests.
    # ------------------------------------------------------------------

    artifacts_root = Path(__file__).parent / "_artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)

    unique = (
        f"data_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:6]}"
    )
    data_dir = artifacts_root / unique
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv(ENV_DATA_DIR, str(data_dir))

    # ------------------------------------------------------------------
    # Port – select a currently-available TCP port.
    # ------------------------------------------------------------------
    def _choose_free_port() -> int:
        for _ in range(50):  # try up to 50 random ports
            port = random.randint(20000, 50000)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    continue  # in use – pick another
                return port
        # Fallback – let the OS pick an unused port (port 0) then reuse it.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    port = _choose_free_port()
    monkeypatch.setenv(ENV_PORT, str(port))

    # ------------------------------------------------------------------
    # Format – ensure tests get JSON output for parsing
    # ------------------------------------------------------------------
    monkeypatch.setenv("PERSISTPROC_FORMAT", "json")

    yield

    # Cleanup: monkeypatch context manager restores env automatically.


@pytest.fixture
def persistproc_data_dir() -> Path:
    """Return the data directory configured for *persistproc* in this test."""
    val = os.environ.get(ENV_DATA_DIR)
    if not val:
        raise RuntimeError("PERSISTPROC_DATA_DIR not set by _persistproc_env")
    return Path(val)


@pytest.fixture
def persistproc_port() -> int:
    """Return the TCP port allocated for *persistproc* in this test."""
    val = os.environ.get(ENV_PORT)
    if not val:
        raise RuntimeError("PERSISTPROC_PORT not set by _persistproc_env")
    return int(val)


# ---------------------------------------------------------------------------
# Helper fixtures for starting/stopping the persistproc server used in e2e tests
# ---------------------------------------------------------------------------


@pytest.fixture
def persistproc_server():
    """Start a persistproc server for the duration of one test."""
    proc = start_persistproc()
    yield proc
    stop_run(proc)


@pytest.fixture
def server(persistproc_server):  # alias for convenience
    return persistproc_server


@pytest.fixture(autouse=True)
def logging_config():
    """Silence overly verbose third-party loggers during tests."""
    # These loggers are very verbose and don't provide useful info for debugging persistproc issues
    noisy_loggers = [
        "httpcore.http11",
        "mcp.server.streamable_http",
        "mcp.server.streamable_http_manager",
        "mcp.server.lowlevel.server",
        "sse_starlette.sse",
        "asyncio",
        "FastMCP.fastmcp.server.server",
        "uvicorn.access",
        "uvicorn.error",
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
