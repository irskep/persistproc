"""Unit tests for ProcessManager using fakes to avoid real processes and threading."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from persistproc.process_manager import ProcessManager, get_label
from tests.fakes import (
    FakeSubprocessPopen,
    create_fake_proc_entry,
    create_fake_registry,
)


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def fake_registry(temp_dir):
    """Create a fake registry with fake dependencies."""
    return create_fake_registry(temp_dir)


@pytest.fixture
def process_manager(fake_registry, temp_dir):
    """Create a ProcessManager with fake dependencies and no monitoring."""
    # Disable monitoring to avoid real threading
    return ProcessManager(
        temp_dir / "server.log",
        monitor=False,
        registry=fake_registry,
        data_dir=temp_dir,
    )


class TestGetLabel:
    """Test the get_label utility function."""

    def test_explicit_label(self, tmp_path):
        """Test that explicit label is used when provided."""
        result = get_label("my-custom-label", "python script.py", str(tmp_path))
        assert result == "my-custom-label"

    def test_generated_label(self):
        """Test that label is generated from command and directory."""
        result = get_label(None, "python script.py", "/home/user")
        assert result == "python script.py in /home/user"

    def test_empty_explicit_label(self, tmp_path):
        """Test that empty string is treated as no explicit label."""
        result = get_label("", "echo hello", str(tmp_path))
        assert result == f"echo hello in {tmp_path}"


class TestProcessManagerInit:
    """Test ProcessManager initialization."""

    def test_init_with_monitoring_disabled(self, fake_registry, temp_dir):
        """Test initialization with monitoring disabled."""
        pm = ProcessManager(
            temp_dir / "server.log",
            monitor=False,
            registry=fake_registry,
            data_dir=temp_dir,
        )
        assert pm.data_dir == temp_dir
        assert pm.monitor is False
        assert pm._monitor_thread is None

    def test_init_with_monitoring_enabled(self, fake_registry, temp_dir):
        """Test initialization with monitoring enabled (but we avoid real threading)."""
        with patch("threading.Thread") as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance

            ProcessManager(
                temp_dir / "server.log",
                monitor=True,
                registry=fake_registry,
                data_dir=temp_dir,
            )

            # Should create and start thread
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()


class TestProcessManagerStart:
    """Test ProcessManager.start() method."""

    @patch("persistproc.process_manager.subprocess.Popen")
    def test_start_success(self, mock_popen, process_manager, tmp_path):
        """Test successful process start."""
        # Setup fake process
        fake_proc = FakeSubprocessPopen(pid=1234)
        mock_popen.return_value = fake_proc

        result = process_manager.start(
            command="echo hello",
            working_directory=tmp_path,
            environment={"TEST": "value"},
            label="test-echo",
        )

        # Verify result
        assert result.pid == 1234
        assert result.label == "test-echo"
        assert result.error is None
        assert "1234.echo_hello.stdout" in str(result.log_stdout)

        # Verify process was stored
        stored_proc = process_manager._storage.get_process_snapshot(1234)
        assert stored_proc is not None
        assert stored_proc.command == ["echo", "hello"]
        assert stored_proc.status == "running"
        assert stored_proc.label == "test-echo"

    @patch("persistproc.process_manager.subprocess.Popen")
    def test_start_with_generated_label(self, mock_popen, process_manager, tmp_path):
        """Test process start with auto-generated label."""
        fake_proc = FakeSubprocessPopen(pid=5678)
        mock_popen.return_value = fake_proc

        result = process_manager.start(
            command="python script.py",
            working_directory=tmp_path,
            label=None,  # No explicit label
        )

        assert result.label == f"python script.py in {tmp_path}"

        stored_proc = process_manager._storage.get_process_snapshot(5678)
        assert stored_proc.label == f"python script.py in {tmp_path}"

    def test_start_duplicate_label_error(self, process_manager, tmp_path):
        """Test that starting process with duplicate running label fails."""
        # Add a running process with same label
        existing_proc = create_fake_proc_entry(
            pid=1111, status="running", label="test-label"
        )
        process_manager._storage.add_process(existing_proc)

        # Try to start another with same label
        result = process_manager.start(
            command="echo test", working_directory=tmp_path, label="test-label"
        )

        assert result.error is not None
        assert "already running" in result.error
        assert "PID 1111" in result.error

    def test_start_invalid_directory(self, process_manager):
        """Test starting process with non-existent directory."""
        result = process_manager.start(
            command="echo test", working_directory=Path("/nonexistent/directory")
        )

        assert result.error is not None
        assert "does not exist" in result.error

    @patch("persistproc.process_manager.subprocess.Popen")
    def test_start_file_not_found(self, mock_popen, process_manager, tmp_path):
        """Test starting non-existent command."""
        mock_popen.side_effect = FileNotFoundError("nonexistent-command")

        result = process_manager.start(
            command="nonexistent-command", working_directory=tmp_path
        )

        assert result.error is not None
        assert "Command not found" in result.error

    @patch("persistproc.process_manager.subprocess.Popen")
    def test_start_permission_error(self, mock_popen, process_manager, tmp_path):
        """Test starting command with permission error."""
        mock_popen.side_effect = PermissionError("permission denied")

        result = process_manager.start(
            command="restricted-command", working_directory=tmp_path
        )

        assert result.error is not None
        assert "Permission denied" in result.error


class TestProcessManagerList:
    """Test ProcessManager.list() method."""

    def test_list_empty(self, process_manager):
        """Test listing when no processes exist."""
        result = process_manager.list()
        assert result.processes == []

    def test_list_with_processes(self, process_manager):
        """Test listing with multiple processes."""
        # Add some test processes
        proc1 = create_fake_proc_entry(pid=1234, label="proc1", status="running")
        proc2 = create_fake_proc_entry(pid=5678, label="proc2", status="exited")

        process_manager._storage.add_process(proc1)
        process_manager._storage.add_process(proc2)

        result = process_manager.list()

        assert len(result.processes) == 2

        # Verify process info conversion
        proc_by_pid = {p.pid: p for p in result.processes}
        assert proc_by_pid[1234].label == "proc1"
        assert proc_by_pid[1234].status == "running"
        assert proc_by_pid[5678].label == "proc2"
        assert proc_by_pid[5678].status == "exited"

    def test_list_with_pid_zero_returns_server_info(self, process_manager):
        """Test that list with pid=0 returns server ProcessInfo."""
        with patch("os.getpid", return_value=9999):
            result = process_manager.list(pid=0)

        # Should return only the server process
        assert len(result.processes) == 1
        server_process = result.processes[0]

        # Verify server process data
        assert server_process.pid == 9999
        assert server_process.label == "persistproc-server"
        assert server_process.status == "running"
        assert server_process.command == ["persistproc", "serve"]


class TestProcessManagerListWithStatus:
    """Test ProcessManager.list() method returning status information."""

    def test_list_with_status_by_pid(self, process_manager):
        """Test getting status by PID via list method."""
        proc = create_fake_proc_entry(pid=1234, command=["python", "script.py"])
        process_manager._storage.add_process(proc)

        result = process_manager.list(pid=1234)

        assert len(result.processes) == 1
        process_info = result.processes[0]
        assert process_info.pid == 1234
        assert process_info.command == ["python", "script.py"]
        assert process_info.status == "running"

    def test_list_with_status_pid_not_found(self, process_manager):
        """Test list method for non-existent PID."""
        result = process_manager.list(pid=9999)

        assert len(result.processes) == 0

    def test_list_with_status_by_label(self, process_manager):
        """Test getting status by label via list method."""
        proc = create_fake_proc_entry(pid=1234, label="my-app")
        process_manager._storage.add_process(proc)

        result = process_manager.list(command_or_label="my-app")

        assert len(result.processes) == 1
        process_info = result.processes[0]
        assert process_info.pid == 1234
        assert process_info.label == "my-app"


class TestProcessManagerStop:
    """Test ProcessManager.stop() method."""

    def test_stop_requires_identifier(self, process_manager):
        """Test that stop requires some identifier."""
        result = process_manager.stop()

        assert result.error is not None
        assert "must be provided" in result.error

    def test_stop_by_pid_success(self, process_manager):
        """Test successful stop by PID."""
        # Create a fake running process
        fake_proc = FakeSubprocessPopen(pid=1234, returncode=None)
        proc_entry = create_fake_proc_entry(pid=1234, status="running", proc=fake_proc)
        process_manager._storage.add_process(proc_entry)

        with (
            patch("persistproc.process_manager.os.killpg"),
            patch("persistproc.process_manager.os.getpgid") as mock_getpgid,
        ):
            mock_getpgid.return_value = 1234

            # Simulate process exiting after SIGTERM
            fake_proc.returncode = 0

            result = process_manager.stop(pid=1234)

        assert result.error is None
        assert result.exit_code == 0

        # Verify process was updated to terminated status
        updated_proc = process_manager._storage.get_process_snapshot(1234)
        assert updated_proc.status == "terminated"

    def test_stop_process_not_running(self, process_manager):
        """Test stopping process that's not running."""
        proc_entry = create_fake_proc_entry(pid=1234, status="exited")
        process_manager._storage.add_process(proc_entry)

        result = process_manager.stop(pid=1234)

        assert result.error is not None
        assert "not running" in result.error


class TestProcessManagerRestart:
    """Test ProcessManager.restart() method."""

    def test_restart_process_not_found(self, process_manager):
        """Test restarting non-existent process."""
        result = process_manager.restart(pid=9999)

        assert result.error is not None
        assert "not found" in result.error.lower()

    @patch("persistproc.process_manager.subprocess.Popen")
    def test_restart_success(self, mock_popen, process_manager, tmp_path):
        """Test successful restart."""
        # Setup original process
        original_proc = FakeSubprocessPopen(pid=1234, returncode=None)
        proc_entry = create_fake_proc_entry(
            pid=1234,
            command=["python", "script.py"],
            working_directory=str(tmp_path),
            status="running",
            proc=original_proc,
        )
        process_manager._storage.add_process(proc_entry)

        # Setup new process after restart
        new_proc = FakeSubprocessPopen(pid=5678)
        mock_popen.return_value = new_proc

        with (
            patch("persistproc.process_manager.os.killpg"),
            patch("persistproc.process_manager.os.getpgid"),
        ):
            # Simulate original process exiting
            original_proc.returncode = 0

            result = process_manager.restart(pid=1234)

        assert result.error is None
        assert result.pid == 5678  # New PID


class TestProcessManagerGetOutput:
    """Test ProcessManager.get_output() method."""

    def test_get_output_process_not_found(self, process_manager):
        """Test getting output for non-existent process."""
        result = process_manager.get_output(pid=9999)

        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_get_output_log_file_missing(self, process_manager, temp_dir):
        """Test getting output when log file doesn't exist."""
        proc_entry = create_fake_proc_entry(pid=1234, log_prefix="1234.test")
        process_manager._storage.add_process(proc_entry)

        result = process_manager.get_output(pid=1234, stream="stdout")

        # Should return empty output for missing file
        assert result.error is None
        assert result.output == []

    def test_get_output_with_log_file(self, process_manager, temp_dir):
        """Test getting output when log file exists."""
        proc_entry = create_fake_proc_entry(pid=1234, log_prefix="1234.test")
        process_manager._storage.add_process(proc_entry)

        # Create a fake log file
        log_file = temp_dir / "process_logs" / "1234.test.stdout"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            "2024-01-01T10:00:00.000Z Hello world\n2024-01-01T10:00:01.000Z Second line\n"
        )

        result = process_manager.get_output(pid=1234, stream="stdout")

        # Debug output if test fails
        if result.error:
            print(f"Error: {result.error}")
        print(f"Log file exists: {log_file.exists()}")
        log_contents = log_file.read_text()
        print(f"Log file contents: {log_contents!r}")
        lines = log_contents.splitlines(keepends=True)
        print(f"Lines from file: {lines}")
        for i, line in enumerate(lines):
            timestamp = line.split(" ", 1)[0] if " " in line else line.strip()
            print(f"Line {i}: timestamp='{timestamp}', full='{line.strip()}'")
        print(f"Result output: {result.output}")

        assert result.error is None
        assert len(result.output) == 2
        assert "Hello world" in result.output[0]
        assert "Second line" in result.output[1]


class TestProcessManagerListWithLogPaths:
    """Test ProcessManager.list() method returning log paths."""

    def test_list_with_log_paths_success(self, process_manager):
        """Test getting log paths via list method for existing process."""
        proc_entry = create_fake_proc_entry(pid=1234, log_prefix="1234.test")
        process_manager._storage.add_process(proc_entry)

        result = process_manager.list(pid=1234)

        assert len(result.processes) == 1
        process_info = result.processes[0]
        assert process_info.pid == 1234
        assert "1234.test.stdout" in process_info.log_stdout
        assert "1234.test.stderr" in process_info.log_stderr
        assert "1234.test.combined" in process_info.log_combined

    def test_list_with_log_paths_not_found(self, process_manager):
        """Test list method for non-existent process."""
        result = process_manager.list(pid=9999)

        assert len(result.processes) == 0


class TestProcessManagerShutdownMethod:
    """Test ProcessManager.shutdown() method."""

    def test_shutdown_no_processes(self, process_manager):
        """Test shutting down persistproc with no managed processes."""
        with (
            patch("os.getpid", return_value=12345),
            patch("threading.Thread") as mock_thread,
        ):
            result = process_manager.shutdown()

            assert result.pid == 12345
            # Should start a thread to kill the server
            mock_thread.assert_called_once()

    def test_shutdown_with_processes(self, process_manager):
        """Test shutting down persistproc with managed processes."""
        # Add some running processes
        proc1 = create_fake_proc_entry(pid=1234, status="running")
        proc2 = create_fake_proc_entry(pid=5678, status="exited")

        process_manager._storage.add_process(proc1)
        process_manager._storage.add_process(proc2)

        with (
            patch("os.getpid", return_value=12345),
            patch("threading.Thread") as mock_thread,
            patch.object(process_manager, "stop") as mock_stop,
        ):
            result = process_manager.shutdown()

            assert result.pid == 12345
            # Should only try to stop running processes
            mock_stop.assert_called_once_with(1234, force=True)
            mock_thread.assert_called_once()


class TestProcessManagerShutdown:
    """Test ProcessManager.shutdown_monitor() method."""

    def test_shutdown_stops_monitoring(self, process_manager):
        """Test that shutdown_monitor stops the monitoring thread."""
        with patch.object(process_manager._storage, "stop_event_set") as mock_stop:
            process_manager.shutdown_monitor()
            mock_stop.assert_called_once()

    def test_shutdown_with_monitor_thread(self, fake_registry, temp_dir):
        """Test shutdown when monitor thread exists."""
        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = Mock()
            mock_thread_cls.return_value = mock_thread

            pm = ProcessManager(
                temp_dir / "server.log",
                monitor=True,
                registry=fake_registry,
                data_dir=temp_dir,
            )

            pm.shutdown_monitor()

            # Should join the thread
            mock_thread.join.assert_called_once_with(timeout=2)


class TestProcessLookup:
    """Test the process lookup functionality."""

    def test_lookup_process_in_snapshot_by_pid(self, process_manager):
        """Test lookup by PID."""
        proc = create_fake_proc_entry(pid=1234)
        snapshot = [proc]

        pid, error = process_manager._lookup_process_in_snapshot(snapshot, pid=1234)

        assert pid == 1234
        assert error is None

    def test_lookup_process_in_snapshot_by_label(self, process_manager):
        """Test lookup by label."""
        proc = create_fake_proc_entry(pid=1234, label="my-app", status="running")
        snapshot = [proc]

        pid, error = process_manager._lookup_process_in_snapshot(
            snapshot, label="my-app"
        )

        assert pid == 1234
        assert error is None

    def test_lookup_process_in_snapshot_by_command(self, process_manager):
        """Test lookup by command."""
        proc = create_fake_proc_entry(
            pid=1234, command=["python", "script.py"], status="running"
        )
        snapshot = [proc]

        pid, error = process_manager._lookup_process_in_snapshot(
            snapshot, command_or_label="python script.py"
        )

        assert pid == 1234
        assert error is None

    def test_lookup_process_in_snapshot_not_found(self, process_manager):
        """Test lookup when process not found."""
        snapshot = []

        pid, error = process_manager._lookup_process_in_snapshot(snapshot, pid=9999)

        assert pid == 9999  # PID passthrough
        assert error is None  # PID lookup doesn't generate errors

        # But label lookup should generate error
        pid, error = process_manager._lookup_process_in_snapshot(
            snapshot, label="nonexistent"
        )

        assert pid is None
        assert error is not None
        assert "No running process found" in error

    def test_lookup_multiple_matches_error(self, process_manager):
        """Test lookup error when multiple processes match command."""
        proc1 = create_fake_proc_entry(
            pid=1234, command=["python", "script.py"], status="running"
        )
        proc2 = create_fake_proc_entry(
            pid=5678, command=["python", "script.py"], status="running"
        )
        snapshot = [proc1, proc2]

        pid, error = process_manager._lookup_process_in_snapshot(
            snapshot, command_or_label="python script.py"
        )

        assert pid is None
        assert error is not None
        assert "Multiple processes found" in error
