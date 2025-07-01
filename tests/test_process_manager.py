import pytest
import signal
from unittest.mock import Mock, patch, MagicMock
import threading
import time

from persistproc import ProcessManager, ProcessInfo


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
        
        with patch.object(pm.log_manager, 'start_logging') as mock_start_logging:
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

    def test_start_process_duplicate_command(self, temp_dir, no_monitor_thread, mock_subprocess):
        """Test starting a process with duplicate command fails."""
        mock_popen, mock_proc = mock_subprocess
        pm = ProcessManager(temp_dir)
        
        with patch.object(pm.log_manager, 'start_logging'):
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
        
        with patch("persistproc.subprocess.Popen", side_effect=FileNotFoundError("nonexistent_command")):
            with pytest.raises(ValueError, match="Command not found"):
                pm.start_process("nonexistent_command")

    def test_stop_process_success(self, temp_dir, no_monitor_thread, mock_killpg, mock_getpgid):
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
            proc=mock_proc
        )
        pm.processes[12345] = process_info
        
        with patch.object(pm, '_log_event'):
            result = pm.stop_process(12345)
            
            # Verify signal was sent
            mock_getpgid.assert_called_once_with(12345)
            mock_killpg.assert_called_once_with(12345, signal.SIGTERM)
            
            # Verify return value
            assert result["pid"] == 12345

    def test_stop_process_force(self, temp_dir, no_monitor_thread, mock_killpg, mock_getpgid):
        """Test forceful process stop."""
        pm = ProcessManager(temp_dir)
        
        # Add a running process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello", 
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello"
        )
        pm.processes[12345] = process_info
        
        with patch.object(pm, '_log_event'):
            pm.stop_process(12345, force=True)
            
            # Verify SIGKILL was sent
            mock_killpg.assert_called_once_with(12345, signal.SIGKILL)

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
            log_prefix="12345.echo_hello"
        )
        pm.processes[12345] = process_info
        
        with pytest.raises(ValueError, match="not running"):
            pm.stop_process(12345)

    def test_stop_process_already_gone(self, temp_dir, no_monitor_thread, mock_getpgid):
        """Test stopping process that's already gone."""
        pm = ProcessManager(temp_dir)
        
        # Add a running process
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running", 
            log_prefix="12345.echo_hello"
        )
        pm.processes[12345] = process_info
        
        with patch("persistproc.os.killpg", side_effect=ProcessLookupError()):
            with patch.object(pm, '_log_event') as mock_log:
                pm.stop_process(12345)
                
                # Should log that process was already gone
                mock_log.assert_called()
                log_message = mock_log.call_args[0][1]
                assert "already gone" in log_message

    def test_list_processes(self, temp_dir, no_monitor_thread):
        """Test listing processes."""
        pm = ProcessManager(temp_dir)
        
        # Add some processes
        process1 = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello"
        )
        process2 = ProcessInfo(
            pid=67890,
            command="sleep 60", 
            start_time="2023-01-01T12:01:00.000Z",
            status="exited",
            log_prefix="67890.sleep_60"
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
            log_prefix="12345.echo_hello"
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

    def test_restart_process_pattern(self, temp_dir, no_monitor_thread, mock_subprocess, mock_killpg, mock_getpgid):
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
            proc=old_proc
        )
        pm.processes[12345] = process_info
        
        with patch.object(pm.log_manager, 'start_logging'):
            with patch.object(pm, '_log_event'):
                # Simulate restart pattern: get info, stop, start
                p_info_dict = pm.get_process_status(12345)
                command = p_info_dict["command"]
                wd = p_info_dict.get("working_directory")
                env = p_info_dict.get("environment")
                
                # Stop old process
                pm.stop_process(12345)
                
                # Start new process
                new_result = pm.start_process(command, wd, env)
                
                # Should stop old process
                mock_killpg.assert_called_once()
                
                # Should start new process
                mock_popen.assert_called_once()
                
                # Should return new process info
                assert new_result["pid"] == 12345  # New process gets same mock PID
                assert new_result["status"] == "running"

    def test_monitor_processes(self, temp_dir, no_monitor_thread):
        """Test process monitoring functionality."""
        pm = ProcessManager(temp_dir)
        
        # Create a mock process that will "exit"
        mock_proc = Mock()
        mock_proc.poll.side_effect = [0]  # Exits with code 0 on first call
        
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello",
            proc=mock_proc
        )
        pm.processes[12345] = process_info
        
        # Run monitor once - process should still be running
        with patch.object(pm, '_log_event'):
            # Manually run one iteration of monitoring
            with pm.lock:
                running_procs = {
                    pid: p for pid, p in pm.processes.items() if p.status == "running"
                }
            
            for pid, p_info in running_procs.items():
                if p_info.proc:
                    exit_code = p_info.proc.poll()
                    if exit_code is not None:
                        with pm.lock:
                            p_info.exit_code = exit_code
                            p_info.exit_time = "2023-01-01T12:00:01.000Z"
                            p_info.status = "exited" if exit_code == 0 else "failed"
                            p_info.proc = None
            
            # Process should be marked as exited
            assert pm.processes[12345].status == "exited"
            assert pm.processes[12345].exit_code == 0

    def test_log_event(self, temp_dir, no_monitor_thread):
        """Test event logging."""
        pm = ProcessManager(temp_dir)
        
        process_info = ProcessInfo(
            pid=12345,
            command="echo hello",
            start_time="2023-01-01T12:00:00.000Z",
            status="running",
            log_prefix="12345.echo_hello"
        )
        
        # Create log file path - LogManager will create the combined file
        log_file = pm.log_directory / f"{process_info.log_prefix}.combined"
        log_file.parent.mkdir(exist_ok=True, parents=True)
        
        with patch("persistproc.logger") as mock_logger:
            pm._log_event(process_info, "Test message")
            
            # Should log to logger
            mock_logger.info.assert_called_once()
            log_message = mock_logger.info.call_args[0][0]
            assert "AUDIT (PID 12345): Test message" in log_message
            
            # Should write to log file
            assert log_file.exists()
            content = log_file.read_text()
            assert "[SYSTEM] Test message" in content