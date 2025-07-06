from __future__ import annotations

from .process_types import (
    KillPersistprocResult,
    ListProcessesResult,
    ProcessLogPathsResult,
    ProcessOutputResult,
    ProcessStatusResult,
    RestartProcessResult,
    StartProcessResult,
    StopProcessResult,
)


def format_start_process_result(result: StartProcessResult) -> str:
    """Format a StartProcessResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    lines = []
    if result.pid is not None:
        lines.append(f"Started process with PID: {result.pid}")
    if result.label:
        lines.append(f"Label: {result.label}")
    if result.log_stdout:
        lines.append(f"Stdout log: {result.log_stdout}")
    if result.log_stderr:
        lines.append(f"Stderr log: {result.log_stderr}")
    if result.log_combined:
        lines.append(f"Combined log: {result.log_combined}")

    return "\n".join(lines) if lines else "Process started successfully"


def format_stop_process_result(result: StopProcessResult) -> str:
    """Format a StopProcessResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    if result.exit_code is not None:
        return f"Process stopped with exit code: {result.exit_code}"
    else:
        return "Process could not be terminated"


def format_process_status_result(result: ProcessStatusResult) -> str:
    """Format a ProcessStatusResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    lines = []
    if result.pid is not None:
        lines.append(f"PID: {result.pid}")
    if result.command:
        lines.append(f"Command: {' '.join(result.command)}")
    if result.working_directory:
        lines.append(f"Working directory: {result.working_directory}")
    if result.status:
        lines.append(f"Status: {result.status}")
    if result.label:
        lines.append(f"Label: {result.label}")

    return "\n".join(lines) if lines else "No process information available"


def format_list_processes_result(result: ListProcessesResult) -> str:
    """Format a ListProcessesResult for human-readable output."""
    if not result.processes:
        return "No processes running"

    lines = []
    for proc in result.processes:
        lines.append(f"PID {proc.pid}: {proc.label} ({proc.status})")
        lines.append(f"  Command: {' '.join(proc.command)}")
        lines.append(f"  Working directory: {proc.working_directory}")
        lines.append("")  # Empty line between processes

    # Remove the last empty line
    if lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_process_output_result(result: ProcessOutputResult) -> str:
    """Format a ProcessOutputResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    if not result.output:
        return "No output available"

    lines = []
    if result.lines_before is not None:
        lines.append(f"Lines before: {result.lines_before}")
    if result.lines_after is not None:
        lines.append(f"Lines after: {result.lines_after}")

    if lines:
        lines.append("")  # Empty line before output

    lines.extend(result.output)

    return "\n".join(lines)


def format_process_log_paths_result(result: ProcessLogPathsResult) -> str:
    """Format a ProcessLogPathsResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    lines = []
    if result.stdout:
        lines.append(f"Stdout log: {result.stdout}")
    if result.stderr:
        lines.append(f"Stderr log: {result.stderr}")

    return "\n".join(lines) if lines else "No log paths available"


def format_restart_process_result(result: RestartProcessResult) -> str:
    """Format a RestartProcessResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    if result.pid is not None:
        return f"Process restarted with PID: {result.pid}"
    else:
        return "Process restart failed"


def format_kill_persistproc_result(result: KillPersistprocResult) -> str:
    """Format a KillPersistprocResult for human-readable output."""
    if result.error:
        return f"Error: {result.error}"

    return f"Killed persistproc server with PID: {result.pid}"


# Mapping from result types to their formatting functions
FORMATTERS = {
    StartProcessResult: format_start_process_result,
    StopProcessResult: format_stop_process_result,
    ProcessStatusResult: format_process_status_result,
    ListProcessesResult: format_list_processes_result,
    ProcessOutputResult: format_process_output_result,
    ProcessLogPathsResult: format_process_log_paths_result,
    RestartProcessResult: format_restart_process_result,
    KillPersistprocResult: format_kill_persistproc_result,
}


def format_result(result: object) -> str:
    """Format any result object for human-readable output."""
    formatter = FORMATTERS.get(type(result))
    if formatter:
        return formatter(result)  # type: ignore
    else:
        return str(result)
