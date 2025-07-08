# Claude Development Notes

## Structure

Typically begin by reading README.md.

Key files:
- persistproc/cli.py
- persistproc/tools.py
- persistproc/process_manager.py

## Running Tests

Use `uv run python -m pytest` to run tests. For development, use `uv run python -m pytest -x --maxfail=3` to stop after 3 failures.

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

**ALWAYS use `git --no-pager diff` for all diffs, never `git diff`.**

## Workflow guidelines

For EVERY programming task assigned, you are NOT FINISHED until you can produce a message in the following format:

<ReportFormat>
After-action report for (task title here)

Relevant files found:
- (list them)

(1-3 paragraphs justifying why the change is both correct and comprehensive)

Steps taken to verify:
- (list them)

Web links supporting my changes:
- (list them)

I solemnly swear there are no further steps I can take to verify the changes within the boundaries set for me.
</ReportFormat>
