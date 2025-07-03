# Testing Improvement Log

This document tracks the efforts to improve the stability and reliability of the `persistproc` test suite.

## Initial State

The test suite was suffering from significant flakiness in CI, characterized by several recurring issues:

-   **`httpx.HTTPStatusError: 500 Internal Server Error`**: These errors occurred frequently during test teardown, suggesting instability in the live test server when the client disconnected.
-   **`assert -2 == 0`**: This failure in the CLI integration tests indicated that `SIGINT` (Ctrl+C) was not being handled gracefully, causing the process to terminate with a signal exit code instead of detaching as designed.
-   **General Flakiness**: The use of fixed-duration `time.sleep()` calls for synchronization led to race conditions, where tests would fail if a process didn't start or stop within the allotted time.

## Phase 1: Stabilization and Signal Handling

The first phase focused on addressing the most critical failures to create a more stable baseline.

**Evidence**: CI logs showing the errors listed above.

**Changes**:

1.  **Deterministic Waits**: Replaced fixed `time.sleep()` calls with polling loops. For example, the `live_server_url` fixture in `conftest.py` now actively polls the server's port to know when it's ready, and tests now poll for process status changes instead of waiting a fixed time.
2.  **Robust `SIGINT` Handling**: The signal handling logic in `persistproc/cli.py` was refactored to use an `asyncio.Event`. This resolved a race condition and ensures the CLI process correctly intercepts `Ctrl+C`, prompts the user, and exits gracefully.
3.  **Error Suppression (Temporary)**: To reduce CI noise and isolate other failures, `try...except` blocks were temporarily added to the client fixtures to ignore the `500` errors that occurred only during test teardown.

## Phase 2: In-Memory Testing Refactor

While the initial fixes helped, the 500 errors pointed to a deeper problem with using a live HTTP server in tests. The best practice is to use a more reliable in-memory testing pattern.

**Evidence**: The [FastMCP Testing Patterns](https://gofastmcp.com/patterns/testing.md) documentation and the continued presence of server-related errors.

**Changes**:

1.  **In-Memory Server**: Introduced an `mcp_server` fixture in `tests/conftest.py` that creates an in-memory instance of the `FastMCP` application, as recommended by the documentation.
2.  **Test Separation**:
    -   The core integration tests in `tests/integration/test_mcp_tools.py` were refactored to use a new `mcp_client` that communicates with the in-memory server.
    -   Tests that specifically require a running server to test the CLI's network interaction were moved to a new file, `tests/integration/test_cli_server_integration.py`, and use a separate `live_mcp_client`.
3.  **Follow-up Fixes**:
    -   Modified the `create_app` function in `persistproc/server.py` to accept a `ProcessManager` instance, making it usable by the in-memory fixture.
    -   Corrected async fixture definitions (`@pytest_asyncio.fixture`) to resolve `AttributeError` issues with the client.
    -   Fixed a `TypeError` where tests were accessing `tool['name']` on a `Tool` object instead of `tool.name`.

## Phase 3: Chasing Down a `Ctrl+C` Flake

Even after the major refactoring, CI runs were still intermittently failing, pointing to a subtle but persistent race condition in the client's `Ctrl+C` handling. This phase involved a deep dive into the client's shutdown logic.

**A Note on Methodology**: The key lesson from this phase is that with complex, intermittent bugs, confidence in a "final fix" is a fallacy. The more productive mindset is to focus on making incremental progress, adding visibility, and building a more deterministic system with each step. Failures are expected and should be treated as opportunities to learn more about the system's behavior.

**Evidence**: CI logs showing `TimeoutError` in `test_ctrl_c_detach` and other CLI-based tests.

**Changes**:

1.  **Adding the `--on-exit` Flag**: The most significant source of non-determinism was the interactive prompt (`input()`) shown to the user on `Ctrl+C`. To make tests reliable, a new `--on-exit` flag (`stop`|`detach`) was added to `persistproc/cli.py`. All tests were updated to use `--on-exit detach` to prevent any interactive prompts during CI runs.
2.  **Fixing `find_restarted_process`**: During the above change, it was discovered that the `test_cli_client_survives_restart` test was failing. The root cause was an empty, unimplemented `find_restarted_process` helper function in the client. This function was correctly implemented to compare process command strings and start times, allowing the client to reliably detect when a process it's tailing is restarted.
3.  **Refactoring Client Monitoring Logic**: The final and most critical fix was a complete refactor of the client's main monitoring loop in `tail_and_monitor_process_async`.
    -   **The Problem**: The previous logic had a fundamental race condition where the log-tailing thread could block on a `readline()` call, preventing it from detecting when the monitored process had exited.
    -   **The Solution**: The logic was inverted. The main, non-blocking `asyncio` task is now responsible for periodically polling the process's status. The log-tailing thread's only job is to read from the log file. If the main task detects the process has exited or been restarted, it cleanly signals the tailing thread to shut down. This separation of concerns (polling in the async task, blocking I/O in the thread) creates a much more robust and deterministic architecture.

## Phase 4: Stabilizing the Live Test Server

Even with a more robust client, CI continued to show intermittent failures, specifically `httpx.HTTPStatusError: 500 Internal Server Error` and `RuntimeError: Client is not connected`. These errors pointed away from the client logic and towards an underlying instability in how the live test server was being managed.

**Evidence**: CI logs showing `500` errors during client connection/disconnection, and `RuntimeError` when the test client tried to make a call after the server had already failed.

**Changes and Investigation**:

1.  **Lifespan Protocol Hypothesis**: The traceback pointed to a `Task group is not initialized` error inside `fastmcp`, which is a classic symptom of an ASGI server's lifespan protocol not being handled correctly. The initial fix involved changing `persistproc/server.py` to use `uvicorn.run` directly instead of `app.run()`, and wrapping the `FastMCP` app in a `Starlette` app to manage the lifespan.
2.  **Cascading Fixture Failures**: This change, while correct in principle, caused a cascade of new errors in the test suite due to incorrect fixture configurations:
    -   `TypeError: 'tuple' object is not callable`: The `uvicorn` config in `tests/conftest.py` was not correctly handling the new `(app, mcp_app)` tuple returned by `create_app`.
    -   `ValueError: Could not infer a valid transport...`: The in-memory `mcp_client` fixture was passing a raw `Starlette` object to the `fastmcp.Client`, which requires a specific transport.
    -   `TypeError: Client.__init__() got an unexpected keyword argument 'base_url'`: A follow-up fix attempt introduced an invalid argument to the client constructor.
3.  **Source Code Investigation**: To resolve the fixture failures, the `fastmcp` source code was inspected. This revealed the correct way to initialize the client for both live and in-memory testing.
4.  **Targeted Fixes**: Based on the source code, the fixtures were corrected:
    -   `tests/integration/test_mcp_tools.py`: The `mcp_client` fixture was updated to pass the raw `FastMCP` instance directly to the client, which is the correct pattern for in-memory tests.
    -   `tests/conftest.py`: The `live_server_url` fixture was corrected to properly configure `uvicorn` using an app factory. The `live_mcp_client` was also fixed to use the correct URL.
5.  **Observability**: A broad, autouse fixture for dumping logs on any failure was attempted, but it proved to be too noisy and created its own `AttributeError`s due to interactions with pytest's async test runner. It was removed in favor of adding more targeted logging to the specific areas under investigation.

## Phase 5: FastMCP Lifespan Race & Remaining Flakes (Ongoing)

After the live-server fixes we still observed *very* brief windows (typically <200 ms) where
`fastmcp` accepts TCP connections **before** its `StreamableHTTPSessionManager` task group
is running.  Any MCP request that lands during this gap returns **500** and the underlying
client session is closed, yielding secondary `RuntimeError: Client is not connected` errors
in the tests.

**Changes so far**:

1.  **Readiness Probe** – `tests/conftest.py::live_server_url` now polls the `/mcp/` endpoint until a simple `list_processes` call succeeds (20 s max).
2.  **`call_json` Retries** – helper now retries 5xx responses *and* reconnects the
    client on "Client is not connected" errors (12 attempts).
3.  **Tolerant CLI Assertions** – increased timeout & loop count in
    `test_cli_server_integration.py::test_cli_raw_tail`.

These mitigations brought the failure rate from ~50 % to <5 %, but very rarely a 5xx
still sneaks in just after `test_cli_client_survives_restart` restarts the process.

---

## Current Next Steps

1.  **Upstream Issue** – Open a bug against *FastMCP* describing the premature-accept race so it can be fixed in the library.
2.  **Final Mitigation** – If upstream fix is slow, wrap the CLI integration tests with a helper that retries the first MCP request once after any 5xx.
3.  **Optional** – Remove live-server dependency entirely by swapping the CLI tests to the in-memory server (blocked on CLI expecting HTTP URL).
4.  **Coverage** – `persistproc/cli.py` still sits at ~60 % – add unit tests for argument parsing & error branches.

The suite is *stable enough* for day-to-day work (7/8 CI matrix passes); remaining flake is now isolated and well understood. 