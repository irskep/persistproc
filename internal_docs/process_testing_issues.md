# Debugging Process Termination Failures in E2E Tests

This document outlines the investigation into a persistent issue where `pytest` end-to-end tests for the `persistproc run` command would hang, eventually failing with a `TimeoutExpired` error. The core of the problem was that child processes spawned during the tests were not being correctly terminated during test cleanup.

## 1. Initial Problem & Test-Side Fixes

The initial problem was observed in two new tests, `test_run_kills_process_on_exit` and `test_run_detach_keeps_process_running`, which use `persistproc run` to manage a long-running script (`tests/scripts/counter.py`). The tests would consistently time out because the `counter.py` process was not being terminated when the test finished.

Our first step was to improve the test suite's process management capabilities:

1.  **Process Groups (`start_new_session`):** We modified our test helpers (`tests/helpers.py`) to launch both the main `persistproc` server and the `persistproc run` command using `subprocess.Popen` with the `start_new_session=True` argument. This ensures that each subprocess is the leader of a new process group.

2.  **Robust Cleanup with `os.killpg`:** We created a new helper function, `stop_run`, which sends signals to the entire process group using `os.killpg(os.getpgid(proc.pid), signal.SIGINT)`. This function implements a robust, staged termination strategy:
    *   It first sends `SIGINT` (graceful shutdown).
    *   It waits and polls for the process to exit.
    *   If the process is still alive, it sends `SIGTERM`.
    *   As a last resort, it sends `SIGKILL`.

This approach was also integrated into the `persistproc_server` fixture in `tests/conftest.py` to ensure reliable server cleanup.

## 2. Identifying the Root Cause: The "Double `setsid`" Problem

Despite the robust test-side cleanup, the tests continued to hang. Further investigation revealed a "double `setsid`" issue in the application logic itself.

The sequence of events was as follows:
1.  The test suite starts `persistproc run` in a new process group (**PGID_A**).
2.  `persistproc run` connects to the `persistproc` server and requests that it start the `counter.py` script.
3.  The server's `ProcessManager` in `persistproc/process_manager.py` would then start `counter.py` using `subprocess.Popen` with `preexec_fn=os.setsid`. This placed the `counter.py` script into a *second*, entirely new process group (**PGID_B**).

The test's cleanup logic would correctly send a kill signal to **PGID_A**, terminating the `persistproc run` process. However, the `counter.py` script in **PGID_B** would not receive the signal, becoming an orphaned process and causing the test to hang.

## 3. External Research & Validation

Our investigation was guided by several external resources:

*   **Python Bug Tracker - [Issue 38502: regrtest: use process groups](https://bugs.python.org/issue38502):** This issue in the CPython test runner (`regrtest`) confirmed that our test-side strategy of using `start_new_session=True` and killing the entire process group is a valid and recommended approach for managing subprocess trees during tests.

*   **Pytest GitHub - [Issue #11174: Test using multiprocessing only hangs when ran with test suite](https://github.com/pytest-dev/pytest/issues/11174):** This issue highlighted the complexities of subprocess management within a test runner on POSIX systems. It explained how the default `fork` start method can lead to hangs due to inherited state (like file descriptors) from the parent `pytest` process. This reinforced our understanding that clean process separation is critical.

## 4. The Implemented Fix

Based on the "double `setsid`" diagnosis, the fix was to remove the redundant session creation from the application code. Since the `persistproc` server is already started in a managed session by our test fixture, any children it spawns should inherit its process group.

The following change was made in `persistproc/process_manager.py`:

```python
# ...
        try:
            proc = subprocess.Popen(  # noqa: S603 – user command
                shlex.split(command),
                cwd=str(working_directory) if working_directory else None,
                env={**os.environ, **(environment or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                # The line below was removed.
                # preexec_fn=os.setsid if os.name != "nt" else None, 
            )
# ...
```

## 5. A Failed Experiment and Reversal

Based on the "double `setsid`" diagnosis, the initial fix attempted was to remove the `preexec_fn=os.setsid` call from `ProcessManager.start_process`.

This proved to be incorrect. It caused a major regression, making the previously passing tests (`test_process_lifecycle` and `test_process_restart`) fail with `httpx.RemoteProtocolError: peer closed connection`. This indicated that the server was being terminated when a test client asked it to stop a child process.

The conclusion is that the `ProcessManager` **must** spawn children in their own process session to isolate them from the server. The `preexec_fn=os.setsid` call was restored.

## 6. Correcting Test Logic

Upon further review, the `test_run_detach_keeps_process_running` test was found to have flawed logic. It was starting a process, then starting a *second* process with `run --on-exit detach`, and then checking the status of the *first* process.

The test was rewritten to correctly verify the detach behavior:
1.  Start a new process using `run --on-exit detach`.
2.  Find the PID of the new process from the server's process list.
3.  Terminate the `run` command itself.
4.  Verify that the new process is still running.
5.  Clean up the orphaned process.

## 7. Current Status (Ongoing)

After restoring the `preexec_fn` call and correcting the test logic, we are back to the original state:
- `test_server_runs_and_responds` passes.
- `test_process_lifecycle` passes.
- `test_process_restart` passes.
- `test_run_kills_process_on_exit` **fails with a timeout.**
- `test_run_detach_keeps_process_running` **fails with a timeout.**

The root cause of the timeout in the two `run` command tests is still unknown. The investigation is ongoing. 