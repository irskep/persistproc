import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from persistproc.utils import get_iso_timestamp, escape_command, get_app_data_dir


class TestUtilityFunctions:
    """Test utility functions that don't depend on external state."""

    def test_get_iso_timestamp(self):
        """Test ISO timestamp generation."""
        timestamp = get_iso_timestamp()

        # Should be a valid ISO format string ending with Z
        assert timestamp.endswith("Z")
        assert "T" in timestamp

        # Should be parseable back to datetime
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_escape_command_basic(self):
        """Test basic command escaping."""
        result = escape_command("echo hello world")
        assert result == "echo_hello_world"

    def test_escape_command_special_chars(self):
        """Test command escaping with special characters."""
        result = escape_command("echo 'hello & world' | grep test")
        assert result == "echo_hello__world__grep_test"

    def test_escape_command_truncation(self):
        """Test command truncation to MAX_COMMAND_LEN."""
        long_command = "a" * 100
        result = escape_command(long_command)
        assert len(result) <= 50  # MAX_COMMAND_LEN

    def test_escape_command_empty(self):
        """Test escaping empty command."""
        result = escape_command("")
        assert result == ""

    @patch("persistproc.utils.sys.platform", "darwin")
    def test_get_app_data_dir_macos(self):
        """Test app data directory on macOS."""
        with patch("persistproc.utils.Path.home") as mock_home:
            from pathlib import Path

            mock_home.return_value = Path("/Users/test")
            result = get_app_data_dir("testapp")
            # Use Path comparison to avoid slash direction issues
            expected = Path("/Users/test/Library/Application Support/testapp")
            assert result == expected

    @patch("persistproc.utils.sys.platform", "linux")
    def test_get_app_data_dir_linux(self):
        """Test app data directory on Linux."""
        with patch("persistproc.utils.Path.home") as mock_home:
            from pathlib import Path

            mock_home.return_value = Path("/home/test")
            result = get_app_data_dir("testapp")
            expected = Path("/home/test/.local/share/testapp")
            assert result == expected

    @patch("persistproc.utils.sys.platform", "freebsd")
    def test_get_app_data_dir_fallback(self):
        """Test app data directory fallback for Unix-like systems."""
        with patch("persistproc.utils.Path.home") as mock_home:
            from pathlib import Path

            mock_home.return_value = Path("/home/test")
            result = get_app_data_dir("testapp")
            expected = Path("/home/test/.testapp")
            assert result == expected
