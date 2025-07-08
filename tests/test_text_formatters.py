"""Unit tests for text formatting functions."""

from persistproc.text_formatters import (
    FORMATTERS,
    format_start_process_result,
    format_stop_process_result,
    format_list_processes_result,
    format_process_output_result,
    format_restart_process_result,
    format_shutdown_result,
    format_result,
)
from persistproc.process_types import (
    StartProcessResult,
    StopProcessResult,
    ListProcessesResult,
    ProcessInfo,
    ProcessOutputResult,
    RestartProcessResult,
    ShutdownResult,
)


class TestStartProcessResultFormatter:
    def test_format_successful_start(self):
        result = StartProcessResult(
            pid=1234,
            label="test process",
            log_stdout="/tmp/out.log",
            log_stderr="/tmp/err.log",
            log_combined="/tmp/combined.log",
        )
        formatted = format_start_process_result(result)
        assert "Started process with PID: 1234" in formatted
        assert "Label: test process" in formatted
        assert "Stdout log: /tmp/out.log" in formatted
        assert "Stderr log: /tmp/err.log" in formatted
        assert "Combined log: /tmp/combined.log" in formatted

    def test_format_error_start(self):
        result = StartProcessResult(error="Failed to start process")
        formatted = format_start_process_result(result)
        assert formatted == "Error: Failed to start process"

    def test_format_minimal_start(self):
        result = StartProcessResult(pid=1234)
        formatted = format_start_process_result(result)
        assert formatted == "Started process with PID: 1234"

    def test_format_empty_start(self):
        result = StartProcessResult()
        formatted = format_start_process_result(result)
        assert formatted == "Process started successfully"


class TestStopProcessResultFormatter:
    def test_format_successful_stop(self):
        result = StopProcessResult(exit_code=0)
        formatted = format_stop_process_result(result)
        assert formatted == "Process stopped with exit code: 0"

    def test_format_error_stop(self):
        result = StopProcessResult(error="Process not found")
        formatted = format_stop_process_result(result)
        assert formatted == "Error: Process not found"

    def test_format_failed_termination(self):
        result = StopProcessResult(exit_code=None)
        formatted = format_stop_process_result(result)
        assert formatted == "Process could not be terminated"


class TestListProcessesResultFormatter:
    def test_format_multiple_processes(self, tmp_path):
        processes = [
            ProcessInfo(
                pid=1234,
                command=["python", "script1.py"],
                working_directory=str(tmp_path),
                status="running",
                label="process 1",
            ),
            ProcessInfo(
                pid=5678,
                command=["node", "server.js"],
                working_directory="/app",
                status="stopped",
                label="process 2",
            ),
        ]
        result = ListProcessesResult(processes=processes)
        formatted = format_list_processes_result(result)

        assert "PID 1234: process 1 (running)" in formatted
        assert "Command: python script1.py" in formatted
        assert f"Working directory: {tmp_path}" in formatted
        assert "PID 5678: process 2 (stopped)" in formatted
        assert "Command: node server.js" in formatted
        assert "Working directory: /app" in formatted

    def test_format_no_processes(self):
        result = ListProcessesResult(processes=[])
        formatted = format_list_processes_result(result)
        assert formatted == "No processes running"

    def test_format_single_process(self, tmp_path):
        processes = [
            ProcessInfo(
                pid=1234,
                command=["python", "script.py"],
                working_directory=str(tmp_path),
                status="running",
                label="test process",
            )
        ]
        result = ListProcessesResult(processes=processes)
        formatted = format_list_processes_result(result)

        assert "PID 1234: test process (running)" in formatted
        assert "Command: python script.py" in formatted
        assert f"Working directory: {tmp_path}" in formatted
        # Should not end with empty line for single process
        assert not formatted.endswith("\n\n")


class TestProcessOutputResultFormatter:
    def test_format_output_with_lines(self):
        result = ProcessOutputResult(
            output=["line 1", "line 2", "line 3"],
            lines_before=10,
            lines_after=5,
        )
        formatted = format_process_output_result(result)
        assert "Lines before: 10" in formatted
        assert "Lines after: 5" in formatted
        assert "line 1" in formatted
        assert "line 2" in formatted
        assert "line 3" in formatted

    def test_format_output_without_metadata(self):
        result = ProcessOutputResult(output=["line 1", "line 2"])
        formatted = format_process_output_result(result)
        assert "line 1" in formatted
        assert "line 2" in formatted
        assert "Lines before:" not in formatted
        assert "Lines after:" not in formatted

    def test_format_error_output(self):
        result = ProcessOutputResult(error="Process not found")
        formatted = format_process_output_result(result)
        assert formatted == "Error: Process not found"

    def test_format_no_output(self):
        result = ProcessOutputResult(output=None)
        formatted = format_process_output_result(result)
        assert formatted == "No output available"

    def test_format_empty_output(self):
        result = ProcessOutputResult(output=[])
        formatted = format_process_output_result(result)
        assert formatted == "No output available"


class TestRestartProcessResultFormatter:
    def test_format_successful_restart(self):
        result = RestartProcessResult(pid=1234)
        formatted = format_restart_process_result(result)
        assert formatted == "Process restarted with PID: 1234"

    def test_format_error_restart(self):
        result = RestartProcessResult(error="Process not found")
        formatted = format_restart_process_result(result)
        assert formatted == "Error: Process not found"

    def test_format_failed_restart(self):
        result = RestartProcessResult(pid=None)
        formatted = format_restart_process_result(result)
        assert formatted == "Process restart failed"


class TestShutdownResultFormatter:
    def test_format_successful_shutdown(self):
        result = ShutdownResult(pid=1234)
        formatted = format_shutdown_result(result)
        assert formatted == "Shutdown persistproc server with PID: 1234"

    def test_format_error_shutdown(self):
        result = ShutdownResult(pid=1234, error="Failed to shutdown")
        formatted = format_shutdown_result(result)
        assert formatted == "Error: Failed to shutdown"


class TestFormatResult:
    def test_format_known_result_type(self):
        result = StartProcessResult(pid=1234)
        formatted = format_result(result)
        assert "Started process with PID: 1234" in formatted

    def test_format_unknown_result_type(self):
        result = "unknown type"
        formatted = format_result(result)
        assert formatted == "unknown type"

    def test_format_all_result_types(self):
        """Test that all result types are properly mapped in FORMATTERS."""

        # Test that all result types have formatters
        result_types = [
            StartProcessResult,
            StopProcessResult,
            ListProcessesResult,
            ProcessOutputResult,
            RestartProcessResult,
            ShutdownResult,
        ]

        for result_type in result_types:
            assert result_type in FORMATTERS, (
                f"Missing formatter for {result_type.__name__}"
            )

        # Test that all formatters can be called
        for result_type, formatter in FORMATTERS.items():
            # Create a minimal instance of each result type
            if result_type == ListProcessesResult:
                test_instance = result_type(processes=[])
            elif result_type == ShutdownResult:
                test_instance = result_type(pid=1234)
            else:
                test_instance = result_type()

            # Should not raise an exception
            formatted = formatter(test_instance)
            assert isinstance(formatted, str)
            assert len(formatted) > 0
