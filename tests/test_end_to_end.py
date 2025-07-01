import pytest
import asyncio
import json
import time
import subprocess
from pathlib import Path
from unittest.mock import patch

from persistproc import server
from persistproc.core import ProcessManager


@pytest.mark.integration
@pytest.mark.slow
class TestEndToEnd:
    """End-to-end integration tests using real processes."""

    def test_real_process_lifecycle(self, temp_dir):
        """Test the complete lifecycle of a real process."""
        pm = ProcessManager(temp_dir)

        # Start a real process using inline Python command
        command = 'python -c "import time; print(\\"Test script started.\\"); [print(i) for i in range(1,4)]; print(\\"Early exit triggered.\\"); exit(0)"'

        pid = None
        try:
            # Start process
            result = pm.start_process(command)
            pid = result["pid"]

            assert result["status"] == "running"
            assert result["command"] == command
            assert pid > 0

            # Process should be in the manager
            assert pid in pm.processes

            # Get status
            status = pm.get_process_status(pid)
            assert status["status"] == "running"

            # Wait for process to exit (test script exits after 3 iterations)
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = pm.get_process_status(pid)
                if status["status"] != "running":
                    break
                time.sleep(0.5)

            # Process should have exited successfully
            final_status = pm.get_process_status(pid)
            assert final_status["status"] == "exited"
            assert final_status["exit_code"] == 0

            # Check log files were created
            log_paths = pm.log_manager.get_log_paths(pm.processes[pid].log_prefix)
            assert log_paths["stdout"].exists()
            assert log_paths["stderr"].exists()
            assert log_paths["combined"].exists()

            # Check log content
            stdout_content = log_paths["stdout"].read_text()
            assert "Test script started." in stdout_content
            assert "Early exit triggered." in stdout_content

        except Exception as e:
            # Clean up if test fails
            if pid and pid in pm.processes:
                try:
                    pm.stop_process(pid)
                except:
                    pass
            raise e

    def test_process_stop_and_restart(self, temp_dir):
        """Test stopping and restarting a real process."""
        pm = ProcessManager(temp_dir)

        # Start a long-running process
        command = 'python -c "import time; print(\\"Test script started.\\"); [time.sleep(0.1) for _ in range(1000)]"'

        pid = None
        new_pid = None
        try:
            # Start process
            result = pm.start_process(command)
            pid = result["pid"]

            # Let it run briefly
            time.sleep(1)

            # Stop process
            stop_result = pm.stop_process(pid)
            assert stop_result["pid"] == pid

            # Wait for process to be marked as terminated
            timeout = 5
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = pm.get_process_status(pid)
                if status["status"] != "running":
                    break
                time.sleep(0.1)

            # Process should be stopped
            final_status = pm.get_process_status(pid)
            assert final_status["status"] in ["exited", "failed", "terminated"]

            # Restart process (simulate restart pattern used in MCP tools)
            # Get process info before stopping
            p_info_dict = pm.get_process_status(pid)
            command = p_info_dict["command"]
            wd = p_info_dict.get("working_directory")
            env = p_info_dict.get("environment")

            # Start new process
            restart_result = pm.start_process(command, wd, env)
            new_pid = restart_result["pid"]

            # Should have a new PID and be running
            assert new_pid != pid
            assert restart_result["status"] == "running"

        except Exception as e:
            # Clean up if test fails
            for cleanup_pid in [pid, new_pid]:
                if cleanup_pid and cleanup_pid in pm.processes:
                    try:
                        pm.stop_process(cleanup_pid)
                    except:
                        pass
            raise e
        finally:
            # Always clean up
            for cleanup_pid in [pid, new_pid]:
                if cleanup_pid and cleanup_pid in pm.processes:
                    try:
                        pm.stop_process(cleanup_pid)
                    except:
                        pass

    def test_duplicate_command_detection(self, temp_dir):
        """Test that duplicate commands are detected correctly."""
        pm = ProcessManager(temp_dir)

        command = 'python -c "import time; print(\\"Test script started.\\"); [time.sleep(0.1) for _ in range(1000)]"'

        pid1 = None
        try:
            # Start first process
            result1 = pm.start_process(command)
            pid1 = result1["pid"]

            # Try to start same command again
            with pytest.raises(ValueError, match="already running"):
                pm.start_process(command)

        except Exception as e:
            # Clean up if test fails
            if pid1 and pid1 in pm.processes:
                try:
                    pm.stop_process(pid1)
                except:
                    pass
            raise e
        finally:
            # Always clean up
            if pid1 and pid1 in pm.processes:
                try:
                    pm.stop_process(pid1)
                except:
                    pass

    def test_mcp_server_real_process(self, temp_dir):
        """Test MCP server with real process management using direct tool simulation."""
        pm = ProcessManager(temp_dir)

        command = 'python -c "import time; print(\\"Test script started.\\"); [print(i) for i in range(1,4)]; print(\\"Early exit triggered.\\"); exit(0)"'

        pid = None
        try:
            with patch.object(server, "process_manager", pm, create=True):
                app = server.create_app()
                # App creation should succeed
                assert app is not None

            # Test MCP tool functions directly (since FastMCP doesn't allow introspection)
            def start_process_tool(
                command: str, working_directory: str = None, environment: dict = None
            ) -> str:
                try:
                    result = pm.start_process(command, working_directory, environment)
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            def list_processes_tool() -> str:
                try:
                    result = pm.list_processes()
                    return json.dumps(result, indent=2)
                except Exception as e:
                    return json.dumps({"error": str(e)})

            def get_process_status_tool(pid: int) -> str:
                try:
                    result = pm.get_process_status(pid)
                    return json.dumps(result, indent=2)
                except (ValueError, RuntimeError) as e:
                    return json.dumps({"error": str(e)})

            # Start process via MCP tool simulation
            start_result = start_process_tool(command=command)
            start_data = json.loads(start_result)

            assert start_data["status"] == "running"
            pid = start_data["pid"]

            # List processes
            list_result = list_processes_tool()
            list_data = json.loads(list_result)

            assert len(list_data) == 1
            assert list_data[0]["pid"] == pid

            # Get status
            status_result = get_process_status_tool(pid=pid)
            status_data = json.loads(status_result)

            assert status_data["pid"] == pid
            assert status_data["status"] == "running"

            # Wait for process to exit
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                status_result = get_process_status_tool(pid=pid)
                status_data = json.loads(status_result)
                if status_data["status"] != "running":
                    break
                time.sleep(0.5)

            # Should have exited successfully
            final_status_result = get_process_status_tool(pid=pid)
            final_status_data = json.loads(final_status_result)
            assert final_status_data["status"] == "exited"

        except Exception as e:
            # Clean up if test fails
            if pid and pid in pm.processes:
                try:
                    pm.stop_process(pid)
                except:
                    pass
            raise e

    def test_log_file_content(self, temp_dir):
        """Test that log files contain expected content."""
        pm = ProcessManager(temp_dir)

        command = 'python -c "import time; print(\\"Test script started.\\"); [print(i) for i in range(1,4)]; print(\\"Early exit triggered.\\"); exit(0)"'

        pid = None
        try:
            # Start process
            result = pm.start_process(command)
            pid = result["pid"]

            # Wait for process to complete
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = pm.get_process_status(pid)
                if status["status"] != "running":
                    break
                time.sleep(0.5)

            # Get log paths
            log_paths = pm.log_manager.get_log_paths(pm.processes[pid].log_prefix)

            # Check stdout log
            stdout_content = log_paths["stdout"].read_text()
            assert "Test script started." in stdout_content
            assert "1" in stdout_content  # Counter output
            assert "2" in stdout_content
            assert "3" in stdout_content
            assert "Early exit triggered." in stdout_content

            # Check combined log includes system messages
            combined_content = log_paths["combined"].read_text()
            assert "[SYSTEM]" in combined_content
            assert "Process started with command:" in combined_content
            assert "Process exited with code 0" in combined_content

            # All timestamps should be in ISO format
            lines = stdout_content.strip().split("\n")
            for line in lines:
                if line.strip():
                    assert line.startswith("2")  # ISO timestamp starts with year
                    assert "T" in line[:20]  # Should have T separator in first 20 chars
                    assert "Z" in line[:30]  # Should have Z timezone in first 30 chars

        except Exception as e:
            # Clean up if test fails
            if pid and pid in pm.processes:
                try:
                    pm.stop_process(pid)
                except:
                    pass
            raise e

    def test_working_directory_and_environment(self, temp_dir):
        """Test that working directory and environment are handled correctly."""
        pm = ProcessManager(temp_dir)

        # Create a test directory
        test_dir = temp_dir / "test_workdir"
        test_dir.mkdir()

        # Use inline Python command that outputs current directory and env var
        command = 'python -c "import os; print(f\\"CWD: {os.getcwd()}\\"); print(f\\"TEST_VAR: {os.environ.get(\'TEST_VAR\', \'NOT_SET\')}\\"); exit(0)"'

        pid = None
        try:
            # Start process with custom working directory and environment
            result = pm.start_process(
                command=command,
                working_directory=str(test_dir),
                environment={"TEST_VAR": "test_value"},
            )
            pid = result["pid"]

            # Wait for process to complete
            timeout = 5
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = pm.get_process_status(pid)
                if status["status"] != "running":
                    break
                time.sleep(0.1)

            # Check log output
            log_paths = pm.log_manager.get_log_paths(pm.processes[pid].log_prefix)
            stdout_content = log_paths["stdout"].read_text()

            # Should show correct working directory and environment variable
            # On macOS, paths may have /private prefix, so check for both
            assert (
                f"CWD: {test_dir}" in stdout_content
                or f"CWD: /private{test_dir}" in stdout_content
            )
            assert "TEST_VAR: test_value" in stdout_content

        except Exception as e:
            # Clean up if test fails
            if pid and pid in pm.processes:
                try:
                    pm.stop_process(pid)
                except:
                    pass
            raise e

    def test_process_output_retrieval(self, temp_dir):
        """Test retrieving process output via the get_process_output method."""
        pm = ProcessManager(temp_dir)

        command = 'python -c "import time; print(\\"Test script started.\\"); [print(i) for i in range(1,4)]; print(\\"Early exit triggered.\\"); exit(0)"'

        pid = None
        try:
            # Start process
            result = pm.start_process(command)
            pid = result["pid"]

            # Wait for process to complete
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = pm.get_process_status(pid)
                if status["status"] != "running":
                    break
                time.sleep(0.5)

            # Test getting output via the API
            stdout_lines = pm.get_process_output(pid, "stdout")
            assert len(stdout_lines) > 0

            # Join and check content
            stdout_content = "".join(stdout_lines)
            assert "Test script started." in stdout_content
            assert "Early exit triggered." in stdout_content

            # Test getting limited lines
            last_lines = pm.get_process_output(pid, "stdout", lines=2)
            assert len(last_lines) <= 2

            # Test getting combined output
            combined_lines = pm.get_process_output(pid, "combined")
            combined_content = "".join(combined_lines)
            assert "Test script started." in combined_content
            assert "[SYSTEM]" in combined_content  # Should include system messages

        except Exception as e:
            # Clean up if test fails
            if pid and pid in pm.processes:
                try:
                    pm.stop_process(pid)
                except:
                    pass
            raise e
