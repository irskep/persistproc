# Claude Development Notes

## Structure

Typically begin by reading README.md.

Key files:
- persistproc/cli.py
- persistproc/tools.py
- persistproc/process_manager.py

## Running Tests

Use `uv run python -m pytest` to run tests. For development, use `uv run python -m pytest -x --maxfail=3` to stop after 3 failures.

There is critical code in tests/conftest.py and tests/helpers.py. Some defaults are changed via env vars.

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

If you get a timeout in tests while running locally, it is NOT a "timing issue" or "race condition." It is as REAL BUG. You are running on a fast computer that is not under load. The correct response to a test timeout is to ADD DEBUG LOGGING and THINK HARD.

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

I solemnly swear there are no further steps I can take to verify the changes within the boundaries set for me. I ran the entire test suite just now, which you can see in the output above. If you can't see a complete passing run of all tests, I admit this whole report is bullshit because I didn't do everything you asked.
</ReportFormat>

## Pitfalls

persistproc/run.py has soft, non-type-safe dependencies on other parts of the program. Audit it carefully, especially after changes to persistproc/tools.py.
