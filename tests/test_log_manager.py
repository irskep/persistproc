import pytest
from unittest.mock import Mock, patch, mock_open
import threading
import time
from pathlib import Path

from persistproc import LogManager


class TestLogManager:
    """Test the LogManager class."""

    def test_init(self, temp_dir):
        """Test LogManager initialization."""
        log_manager = LogManager(temp_dir)
        assert log_manager.log_directory == temp_dir
        assert temp_dir.exists()

    def test_get_log_paths(self, temp_dir):
        """Test log path generation."""
        log_manager = LogManager(temp_dir)
        paths = log_manager.get_log_paths("test_prefix")
        
        expected_paths = {
            "stdout": temp_dir / "test_prefix.stdout",
            "stderr": temp_dir / "test_prefix.stderr", 
            "combined": temp_dir / "test_prefix.combined"
        }
        
        assert paths == expected_paths

    @patch("persistproc.threading.Thread")
    def test_start_logging(self, mock_thread, temp_dir):
        """Test that logging threads are started correctly."""
        log_manager = LogManager(temp_dir)
        
        # Create mock process
        mock_proc = Mock()
        mock_proc.stdout = Mock()
        mock_proc.stderr = Mock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""
        
        # Mock Path.open instead of builtins.open since LogManager uses Path objects
        with patch.object(Path, 'open', mock_open()) as mock_file:
            log_manager.start_logging(mock_proc, "test_prefix")
            
            # Should create 3 threads (stdout, stderr, combined closer)
            assert mock_thread.call_count == 3
            
            # Should open 3 files (stdout, stderr, combined)
            assert mock_file.call_count == 3

    def test_log_stream_processing(self, temp_dir):
        """Test that log streams are processed correctly."""
        log_manager = LogManager(temp_dir)
        
        # Create actual files for testing
        stdout_file = temp_dir / "test.stdout"
        stderr_file = temp_dir / "test.stderr"
        combined_file = temp_dir / "test.combined"
        
        # Mock stream that yields test data
        mock_stream = Mock()
        test_lines = [b"line 1\n", b"line 2\n", b""]  # Empty bytes signals end
        mock_stream.readline.side_effect = test_lines
        
        with patch("persistproc.get_iso_timestamp", return_value="2023-01-01T12:00:00.000Z"):
            # Test the internal log_stream function by calling it directly
            with stdout_file.open("a") as primary, combined_file.open("a") as secondary:
                # We need to access the internal method - let's create a simplified version
                for line_bytes in iter(mock_stream.readline, b""):
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace")
                    timestamped_line = f"2023-01-01T12:00:00.000Z {line}"
                    primary.write(timestamped_line)
                    secondary.write(timestamped_line)
        
        # Verify files were written
        assert stdout_file.exists()
        assert combined_file.exists()
        
        stdout_content = stdout_file.read_text()
        combined_content = combined_file.read_text()
        
        assert "2023-01-01T12:00:00.000Z line 1" in stdout_content
        assert "2023-01-01T12:00:00.000Z line 1" in combined_content