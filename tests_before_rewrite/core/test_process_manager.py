import pytest
import signal
from unittest.mock import Mock, patch, MagicMock, mock_open
import threading
import time

from persistproc.core import ProcessManager, ProcessInfo


class TestProcessManager:
    """Test the ProcessManager class."""

    def test_init(self, temp_dir, no_monitor_thread):
        """Test ProcessManager initialization."""
        pm = ProcessManager(temp_dir)
        assert pm.log_directory == temp_dir
        assert pm.processes == {}
        assert isinstance(pm.lock, type(threading.Lock()))

    def test_start_process_success(self, temp_dir, no_monitor_thread, mock_subprocess):
        """Test successful process start."""
        mock_popen, mock_proc = mock_subprocess
        pm = ProcessManager(temp_dir)

        with patch.object(pm.log_manager, "start_logging") as mock_start_logging:
            result = pm.start_process("echo hello")

            # Verify subprocess was called correctly
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args
            assert call_args[0][0] == ["echo", "hello"]  # shlex.split result

            # Verify process was registered
            assert 12345 in pm.processes
            process_info = pm.processes[12345]
            assert process_info.pid == 12345
            assert process_info.command == "echo hello"
            assert process_info.status == "running"

            # Verify logging was started
            mock_start_logging.assert_called_once()

            # Verify return value
            assert result["pid"] == 12345
            assert result["status"] == "running"

    def test_start_process_duplicate_command(
        self, temp_dir, no_monitor_thread, mock_subprocess
    ):
        """Test starting a process with duplicate command fails."""
        mock_popen, mock_proc = mock_subprocess
        pm = ProcessManager(temp_dir)

        with patch.object(pm.log_manager, "start_logging"):
            # Start first process
            pm.start_process("echo hello")

            # Try to start duplicate
            with pytest.raises(ValueError, match="already running"):
                pm.start_process("echo hello")

    def test_start_process_invalid_working_directory(self, temp_dir, no_monitor_thread):
        """Test starting process with invalid working directory."""
        pm = ProcessManager(temp_dir)

        with pytest.raises(ValueError, match="does not exist"):
            pm.start_process("echo hello", working_directory="/nonexistent/path")

    def test_start_process_command_not_found(self, temp_dir, no_monitor_thread):
        """Test starting process with non-existent command."""
        pm = ProcessManager(temp_dir)

        with patch(
            "persistproc.core.subprocess.Popen",
            side_effect=FileNotFoundError("nonexistent_command"),
        ):
            with pytest.raises(ValueError, match="Command not found"):
                pm.start_process("nonexistent_command")

    def test_stop_process_success(self, temp_dir, no_monitor_thread, mock_killpg):
        """Test successful process stop."""
        pm = ProcessManager(temp_dir)

        # Add a running process
        mock_proc = Mock()
        mock_proc.pid = 12345
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello",
            proc=mock_proc,
        )
        pm.processes[12345] = process_info

        with patch.object(pm, "_log_event"):
            result = pm.stop_process(12345)

            # Verify signal was sent
            mock_killpg["getpgid"].assert_called_once_with(12345)
            mock_killpg["unix_kill"].assert_called_once_with(12345, signal.SIGTERM)

            # Verify return value
            assert result["pid"] == 12345

    def test_stop_process_force(self, temp_dir, no_monitor_thread, mock_killpg):
        """Test forceful process stop."""
        pm = ProcessManager(temp_dir)

        # Add a running process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello",
        )
        pm.processes[12345] = process_info

        with patch.object(pm, "_log_event"):
            pm.stop_process(12345, force=True)

            # Verify SIGKILL was sent
            mock_killpg["unix_kill"].assert_called_once_with(12345, signal.SIGKILL)

    def test_stop_process_not_found(self, temp_dir, no_monitor_thread):
        """Test stopping non-existent process."""
        pm = ProcessManager(temp_dir)

        with pytest.raises(ValueError, match="not found"):
            pm.stop_process(99999)

    def test_stop_process_not_running(self, temp_dir, no_monitor_thread):
        """Test stopping non-running process."""
        pm = ProcessManager(temp_dir)

        # Add an exited process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="exited",
            log_prefix="12345.echo_hello",
        )
        pm.processes[12345] = process_info

        # Stop should not raise, but log a warning and return the current state.
        result = pm.stop_process(12345)
        assert result["status"] == "exited"

    def test_stop_process_already_gone(self, temp_dir, no_monitor_thread, mock_killpg):
        """Test stopping a process that has already been killed externally."""
        pm = ProcessManager(temp_dir)

        # Add a running process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello",
        )
        pm.processes[12345] = process_info

        with (
            patch.object(
                pm, "_send_signal", side_effect=ProcessLookupError()
            ) as mock_send,
            patch.object(pm, "_log_event") as mock_log,
        ):
            pm.stop_process(12345)

            # Should log that process was already gone
            mock_log.assert_called()
            log_message = mock_log.call_args[0][1]
            assert "already gone" in log_message

        # Verify old process is gone (or marked as stopped)
        assert pm.processes[12345].status == "terminated"

    def test_list_processes(self, temp_dir, no_monitor_thread):
        """Test listing processes."""
        pm = ProcessManager(temp_dir)

        # Add some processes
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

        pm.processes[12345] = process1
        pm.processes[67890] = process2

        result = pm.list_processes()

        assert len(result) == 2
        assert any(p["pid"] == 12345 for p in result)
        assert any(p["pid"] == 67890 for p in result)

    def test_get_process_status(self, temp_dir, no_monitor_thread):
        """Test getting process status."""
        pm = ProcessManager(temp_dir)

        # Add a process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello",
        )
        pm.processes[12345] = process_info

        result = pm.get_process_status(12345)

        assert result["pid"] == 12345
        assert result["status"] == "running"
        assert result["command"] == "echo hello"

    def test_get_process_status_not_found(self, temp_dir, no_monitor_thread):
        """Test getting status of non-existent process."""
        pm = ProcessManager(temp_dir)

        with pytest.raises(ValueError, match="not found"):
            pm.get_process_status(99999)

    def test_restart_process_pattern(
        self, temp_dir, no_monitor_thread, mock_subprocess, mock_killpg
    ):
        """Test restarting a process using the same pattern as MCP tools."""
        mock_popen, mock_proc = mock_subprocess
        pm = ProcessManager(temp_dir)

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
        pm.processes[12345] = process_info

        # --- "Restart" ---
        # 1. Get process info
        p_info_dict = pm.get_process_status(12345)
        command = p_info_dict["command"]
        wd = p_info_dict.get("working_directory")
        env = p_info_dict.get("environment")

        # 2. Stop old process
        pm.stop_process(12345)
        # In a real scenario, we'd wait for it to be confirmed stopped
        pm.processes[12345].status = "terminated"

        # 3. Start new process
        # Change the mock PID for the new process
        mock_proc.pid = 54321
        with patch.object(pm.log_manager, "start_logging"):
            new_result = pm.start_process(command, wd, env)

        # Verify new process is running
        assert new_result["pid"] == 54321
        assert new_result["status"] == "running"
        assert 54321 in pm.processes
        assert pm.processes[54321].command == "echo hello"

        # Verify old process is gone (or marked as stopped)
        assert pm.processes[12345].status == "terminated"

    def test_monitor_processes(self, temp_dir):
        """Test that the monitor correctly identifies and handles exited processes."""
        pm = ProcessManager(temp_dir)

        # Add a process with a mock Popen object
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = 0  # Process has exited with code 0
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            status="running",
            proc=mock_proc,
            log_prefix="test",
            start_time="time",
        )
        pm.processes[12345] = process_info

        # Let the monitor thread run
        time.sleep(1.5)

        with patch.object(pm, "_log_event") as mock_log:
            # Verify process status is updated
            assert pm.processes[12345].status == "exited"
            assert pm.processes[12345].exit_code == 0
            assert pm.processes[12345].proc is None  # Should be cleared

            # The log event is now called inside the monitor thread,
            # so we can't reliably capture it here without more complex thread mocking.
            # We will rely on the status change being correct.

    def test_log_event(self, temp_dir, no_monitor_thread):
        """Test that events are logged to the process-specific log file."""
        pm = ProcessManager(temp_dir)
        p_info = ProcessInfo(
            pid=1, command="cmd", status="running", log_prefix="1.cmd", start_time="t"
        )

        # Create a mock for the file handle and the context manager
        mock_file_handle = MagicMock()
        mock_open_context = MagicMock()
        mock_open_context.__enter__.return_value = mock_file_handle

        # Patch Path.open to return our context manager mock
        with patch(
            "pathlib.Path.open", return_value=mock_open_context
        ) as mock_open_method:
            pm._log_event(p_info, "test message")

            # Verify that open was called with 'a' on a Path object
            mock_open_method.assert_called_once_with("a")

            # Verify that write was called on the file handle
            mock_file_handle.write.assert_called_once()
            written_content = mock_file_handle.write.call_args[0][0]
            assert "test message" in written_content
            assert "Z" in written_content

    def test_stop_process_timeout_escalation(self, temp_dir, no_monitor_thread):
        """Verify SIGTERM is followed by SIGKILL after a timeout."""
        pm = ProcessManager(temp_dir)
        proc_mock = MagicMock()
        proc_mock.pid = 123
        # Simulate poll() returning None (still running) for a while
        proc_mock.poll.return_value = None
        pm.processes[123] = ProcessInfo(
            pid=123,
            command="cmd",
            status="running",
            proc=proc_mock,
            start_time="",
            log_prefix="",
        )

        with (
            patch.object(pm, "_send_signal") as mock_send_signal,
            patch.object(pm, "_wait_for_exit", side_effect=[False, True]) as mock_wait,
        ):
            pm.stop_process(123)
            # We expect two calls: SIGTERM then SIGKILL
            assert mock_send_signal.call_count == 2
            mock_send_signal.assert_any_call(123, signal.SIGTERM)
            mock_send_signal.assert_any_call(123, signal.SIGKILL)
            assert mock_wait.call_count == 2

    def test_stop_process_force_kill(self, temp_dir, no_monitor_thread):
        """Verify force=True sends SIGKILL immediately."""
        pm = ProcessManager(temp_dir)
        proc_mock = MagicMock()
        proc_mock.pid = 123
        pm.processes[123] = ProcessInfo(
            pid=123,
            command="cmd",
            status="running",
            proc=proc_mock,
            start_time="",
            log_prefix="",
        )

        with patch.object(pm, "_send_signal") as mock_send_signal:
            pm.stop_process(123, force=True)
            # Should only be one call, and it should be SIGKILL
            mock_send_signal.assert_called_once_with(123, signal.SIGKILL)
