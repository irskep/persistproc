# Handling Intermittent 500 Errors in PersistProc Test Runs

> **Scope**: This note is internal to the PersistProc project. It
> documents why we sometimes see transient *500 Internal Server Error*
> responses from the live FastMCP server and the layered mitigations we
> have added.  Keep this around for future maintainers until the upstream
> FastMCP issue is fixed.

---

## 1  Root Cause (FastMCP race)

FastMCP starts an HTTP listener **before** its
`StreamableHTTPSessionManager` task-group is guaranteed to be running. In
that ~⟨50–200 ms⟩ window any request that hits `/mcp/` bubbles up as:

```
RuntimeError: Task group is not initialized. Make sure to use run().
```

Uvicorn converts the exception to a **500** response, closing the
connection.  Clients that were re-using a keep-alive session then raise
`RuntimeError("Client is not connected")` on their next attempt.

The race is hard to reproduce locally but happens in CI when the server
(or a restarted process) is under heavier load.  Only the first request
after the accept window fails; all subsequent requests succeed once the
task-group is alive.

---

## 2  Why It Matters for the Test Suite

1. **CLI integration tests** start an external `persistproc` CLI process
   which immediately calls `list_processes`. If that very first call
   lands in the gap the CLI crashes and the test fails.
2. **Tool integration tests** use the Python `fastmcp.Client` directly.
   A 500 at exactly the wrong time closes the underlying HTTP/2 session,
   so the *next* call raises `RuntimeError` and the polling helper gives
   up.

Because both scenarios are timing-sensitive they appear as "flakes"
(where 1/8 or 1/16 CI runs fail).

---

## 3  Mitigation Layers We Added

| Layer | Fixture / Helper | Idea | Status |
|-------|------------------|------|--------|
| **L0** | `live_server_url` probe | Block until *two* consecutive `list_processes` calls succeed before yielding the server URL. | ✅ Implemented |
| **L1** | `call_json()` | Retry 5xx responses and silently reconnect the `fastmcp.Client` up to 24× with back-off. | ✅ Implemented |
| **L2** | CLI tests | Extra tolerance (longer loops & timeouts) plus graceful cleanup if the subprocess already exited. | ✅ Implemented |
| **L3** | Upstream patch | Delay FastMCP's `uvicorn.Server.run()` call until `session_manager.run().__aenter__()` completes, eliminating the race. | 🔜 Open issue upstream |

With L0–L2 in place we reduced the failure rate from ≈50 % → <2 %.

---

## 4  Long-Term Options

1. **Upstream fix** (preferred) – when FastMCP changes its startup order
   our probes / retries become unnecessary.
2. **Monkey-patch** FastMCP during tests to block until the task-group is
   ready (risk: diverges from production behaviour).
3. **Remove live-server dependency** – run *all* integration tests
   against the in-memory FastMCP instance.  CLI tests would require
   refactoring the CLI to accept an *app* instead of a URL.

---

## 5  Checklist for New Tests

* Use the existing fixtures (`live_mcp_client`, `call_json`, etc.).
* Avoid `time.sleep()` for synchronisation – prefer polling helpers.
* If you see **500** or "Client is not connected" failures, ensure your
  test goes through the helper stack so the retries kick in.

---

_Last updated: 2025-07-02_ 