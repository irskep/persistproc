# Claude Development Notes

## Dependency Management

**IMPORTANT**: This project uses `mise` for tool management and task automation. To install dependencies, use:

```bash
mise run deps:sync
```

This runs `uv sync --extra docs --extra dev` with the correct extras. Do NOT run `uv sync` directly as it may not include required development dependencies.

## Running Tests

Use `uv run python -m pytest` to run tests.

Tests have a 120-second timeout configured via `pytest-timeout`. This prevents infinite hangs on all platforms including Windows.

## Linting and Type Checking

- Linting: `uv run ruff check`
- Formatting: `uv run ruff format`

## Development Guidelines

**NEVER run persistproc commands manually during development**. The persistproc CLI should only be invoked through the test suite. Manual CLI usage can interfere with test servers and cause unexpected failures.

Instead:
- Use the test suite to verify functionality
- Use the test helpers in `tests/helpers.py` for programmatic testing
- Debug issues through test output and logging

**NEVER background a process with an `&` suffix.**