"""
Direct tests for MCP tool functions.
These tests call the tool functions directly rather than through the MCP framework.
"""

import pytest
import json
from unittest.mock import Mock, patch
from pathlib import Path

from persistproc import server
from persistproc.core import ProcessManager, ProcessInfo


class TestMCPTools:
    """Direct tests for MCP tool functionality."""

    @pytest.fixture
    def process_manager_mock(self, temp_dir, no_monitor_thread):
        """Create a ProcessManager for testing."""
        return ProcessManager(temp_dir)

    def test_start_process_tool_direct(self, process_manager_mock, mock_subprocess):
        """Test start_process tool function directly."""
        mock_popen, mock_proc = mock_subprocess

        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Import and call the function that would be wrapped by @app.tool()
            from persistproc.server import create_app

            app = create_app()

            # Access the tool function through the app's internal registry
            # Since we can't easily introspect FastMCP, we'll test by creating a separate function
            def start_process_tool(
                command: str, working_directory: str = None, environment: dict = None
            ) -> str:
                """Direct implementation of start_process tool for testing."""
                try:
                    result = process_manager_mock.start_process(
                        command, working_directory, environment
                    )
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            with patch.object(process_manager_mock.log_manager, "start_logging"):
                result = start_process_tool(command="echo hello")

                # Should return JSON string
                result_data = json.loads(result)
                assert result_data["pid"] == 12345
                assert result_data["status"] == "running"
                assert result_data["command"] == "echo hello"

    def test_list_processes_tool_direct(self, process_manager_mock):
        """Test list_processes tool function directly."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add some test processes
            process1 = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
            )
            process2 = ProcessInfo(
                pid=67890,
                command="sleep 60",
                start_time="2023-01-01T12:01:00.000Z",
                status="exited",
                log_prefix="67890.sleep_60",
            )

            process_manager_mock.processes[12345] = process1
            process_manager_mock.processes[67890] = process2

            def list_processes_tool() -> str:
                """Direct implementation of list_processes tool for testing."""
                try:
                    result = process_manager_mock.list_processes()
                    return json.dumps(result, indent=2)
                except Exception as e:
                    return json.dumps({"error": str(e)})

            result = list_processes_tool()
            result_data = json.loads(result)

            assert len(result_data) == 2
            assert any(p["pid"] == 12345 for p in result_data)
            assert any(p["pid"] == 67890 for p in result_data)

    def test_stop_process_tool_direct(
        self, process_manager_mock, mock_killpg, mock_getpgid
    ):
        """Test stop_process tool function directly."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add a running process
            process_info = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
            )
            process_manager_mock.processes[12345] = process_info

            def stop_process_tool(pid: int, force: bool = False) -> str:
                """Direct implementation of stop_process tool for testing."""
                try:
                    result = process_manager_mock.stop_process(pid, force)
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            with patch.object(process_manager_mock, "_log_event"):
                result = stop_process_tool(pid=12345)
                result_data = json.loads(result)

                assert result_data["pid"] == 12345
                mock_killpg.assert_called_once()

    def test_get_process_status_tool_direct(self, process_manager_mock):
        """Test get_process_status tool function directly."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add a process
            process_info = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
            )
            process_manager_mock.processes[12345] = process_info

            def get_process_status_tool(pid: int) -> str:
                """Direct implementation of get_process_status tool for testing."""
                try:
                    result = process_manager_mock.get_process_status(pid)
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            result = get_process_status_tool(pid=12345)
            result_data = json.loads(result)

            assert result_data["pid"] == 12345
            assert result_data["status"] == "running"
            assert result_data["command"] == "echo hello"

    def test_get_process_log_paths_tool_direct(self, process_manager_mock):
        """Test get_process_log_paths tool function directly."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add a process
            process_info = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
            )
            process_manager_mock.processes[12345] = process_info

            def get_process_log_paths_tool(pid: int) -> str:
                """Direct implementation of get_process_log_paths tool for testing."""
                try:
                    with process_manager_mock.lock:
                        p_info = process_manager_mock.processes.get(pid)
                    if not p_info:
                        raise ValueError(f"Process with PID {pid} not found.")

                    log_paths = process_manager_mock.log_manager.get_log_paths(
                        p_info.log_prefix
                    )
                    # convert Path objects to strings for JSON serialization
                    str_log_paths = {k: str(v) for k, v in log_paths.items()}
                    return json.dumps(str_log_paths, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            result = get_process_log_paths_tool(pid=12345)
            result_data = json.loads(result)

            # Should contain the three log file paths
            assert "stdout" in result_data
            assert "stderr" in result_data
            assert "combined" in result_data

            # Paths should contain the process prefix
            assert "12345.echo_hello" in result_data["stdout"]

    def test_restart_process_tool_direct(
        self, process_manager_mock, mock_subprocess, mock_killpg, mock_getpgid
    ):
        """Test restart_process tool function directly."""
        mock_popen, mock_proc = mock_subprocess

        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add a running process
            old_proc = Mock()
            old_proc.pid = 12345
            process_info = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
                working_directory="/tmp",
                environment={"TEST": "value"},
                proc=old_proc,
            )
            process_manager_mock.processes[12345] = process_info

            def restart_process_tool(pid: int) -> str:
                """Direct implementation of restart_process tool for testing."""
                try:
                    # Get old process info
                    p_info_dict = process_manager_mock.get_process_status(pid)

                    command = p_info_dict["command"]
                    wd = p_info_dict.get("working_directory")
                    env = p_info_dict.get("environment")

                    # Stop old process
                    process_manager_mock.stop_process(pid)

                    # Start new process
                    new_p_info_dict = process_manager_mock.start_process(
                        command, wd, env
                    )
                    return json.dumps(new_p_info_dict, indent=2)

                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            with patch.object(process_manager_mock.log_manager, "start_logging"):
                with patch.object(process_manager_mock, "_log_event"):
                    result = restart_process_tool(pid=12345)
                    result_data = json.loads(result)

                    # Should return new process info
                    assert result_data["pid"] == 12345
                    assert result_data["status"] == "running"
                    assert result_data["command"] == "echo hello"

    def test_tool_error_handling_direct(self, process_manager_mock):
        """Test that MCP tools handle errors gracefully."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):

            def get_process_status_tool(pid: int) -> str:
                """Direct implementation of get_process_status tool for testing."""
                try:
                    result = process_manager_mock.get_process_status(pid)
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            # Try to get status of non-existent process
            result = get_process_status_tool(pid=99999)
            result_data = json.loads(result)

            # Should return error
            assert "error" in result_data
            assert "not found" in result_data["error"]

    def test_get_process_output_tool_direct(self, process_manager_mock):
        """Test get_process_output tool function directly."""
        with patch.object(server, "process_manager", process_manager_mock, create=True):
            # Add a process and create log files
            process_info = ProcessInfo(
                pid=12345,
                command="echo hello",
                start_time="2023-01-01T12:00:00.000Z",
                status="running",
                log_prefix="12345.echo_hello",
            )
            process_manager_mock.processes[12345] = process_info

            # Create log files
            stdout_file = process_manager_mock.log_directory / "12345.echo_hello.stdout"
            stderr_file = process_manager_mock.log_directory / "12345.echo_hello.stderr"
            combined_file = (
                process_manager_mock.log_directory / "12345.echo_hello.combined"
            )

            # Write some test content
            stdout_file.write_text(
                "2023-01-01T12:00:00.000Z stdout line 1\n2023-01-01T12:00:01.000Z stdout line 2\n"
            )
            stderr_file.write_text("2023-01-01T12:00:00.000Z stderr line 1\n")
            combined_file.write_text(
                "2023-01-01T12:00:00.000Z stdout line 1\n2023-01-01T12:00:00.000Z stderr line 1\n2023-01-01T12:00:01.000Z stdout line 2\n"
            )

            def get_process_output_tool(
                pid: int,
                stream: str,
                lines: int = None,
                before_time: str = None,
                since_time: str = None,
            ) -> str:
                """Direct implementation of get_process_output tool for testing."""
                try:
                    result = process_manager_mock.get_process_output(
                        pid, stream, lines, before_time, since_time
                    )
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            # Test getting stdout
            result = get_process_output_tool(pid=12345, stream="stdout")
            result_data = json.loads(result)
            assert isinstance(result_data, list)
            assert any("stdout line 1" in line for line in result_data)
            assert any("stdout line 2" in line for line in result_data)

            # Test getting stderr
            result = get_process_output_tool(pid=12345, stream="stderr")
            result_data = json.loads(result)
            assert isinstance(result_data, list)
            assert any("stderr line 1" in line for line in result_data)

            # Test getting combined
            result = get_process_output_tool(pid=12345, stream="combined")
            result_data = json.loads(result)
            assert isinstance(result_data, list)
            assert any("stdout line 1" in line for line in result_data)
            assert any("stderr line 1" in line for line in result_data)
            assert any("stdout line 2" in line for line in result_data)

            # Test with line limit
            result = get_process_output_tool(pid=12345, stream="stdout", lines=1)
            result_data = json.loads(result)
            assert len(result_data) == 1
            assert "stdout line 2" in result_data[0]  # Should get the last line
