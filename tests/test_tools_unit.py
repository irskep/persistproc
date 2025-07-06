"""Unit tests for tools.py using mocks/fakes to avoid real MCP calls."""

import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from persistproc.process_manager import ProcessManager
from persistproc.tools import (
    ALL_TOOL_CLASSES,
    GetProcessLogPathsTool,
    GetProcessOutputTool,
    GetProcessStatusTool,
    KillPersistprocTool,
    ListProcessesTool,
    RestartProcessTool,
    StartProcessTool,
    StopProcessTool,
    _parse_target_to_pid_or_command_or_label,
)
from persistproc.mcp_client_utils import execute_mcp_request


class TestParseTargetToPidOrCommandOrLabel:
    """Test the helper function for parsing target arguments."""

    def test_parse_pid_only(self):
        """Test parsing a single PID argument."""
        pid, command_or_label = _parse_target_to_pid_or_command_or_label("123", [])
        assert pid == 123
        assert command_or_label is None

    def test_parse_invalid_pid(self):
        """Test parsing non-numeric target as command."""
        pid, command_or_label = _parse_target_to_pid_or_command_or_label("python", [])
        assert pid is None
        assert command_or_label == "python"

    def test_parse_command_with_args(self):
        """Test parsing command with arguments."""
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            "python", ["-m", "http.server"]
        )
        assert pid is None
        assert command_or_label == "python -m http.server"

    def test_parse_label_with_spaces(self):
        """Test parsing label/command with spaces."""
        pid, command_or_label = _parse_target_to_pid_or_command_or_label(
            "my web server", []
        )
        assert pid is None
        assert command_or_label == "my web server"


class TestMCPRequest:
    """Test the MCP request helper function."""

    @patch("persistproc.mcp_client_utils.make_client")
    @patch("persistproc.tools.asyncio.run")
    def testexecute_mcp_request_success(self, mock_asyncio_run, mock_make_client):
        """Test successful MCP request."""
        # Setup mock client
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.text = '{"result": "success"}'
        mock_client.call_tool.return_value = [mock_result]
        mock_make_client.return_value.__aenter__.return_value = mock_client

        # Setup mock asyncio.run to call the async function
        def run_coro(coro):
            # Simulate the async function execution
            import asyncio

            return asyncio.get_event_loop().run_until_complete(coro)

        mock_asyncio_run.side_effect = run_coro

        # Mock print to capture output
        with patch("builtins.print") as mock_print:
            execute_mcp_request("test_tool", 8947, {"param": "value"})

            # Verify print was called with JSON response
            mock_print.assert_called_once_with('{\n  "result": "success"\n}')

    @patch("persistproc.mcp_client_utils.make_client")
    @patch("persistproc.tools.asyncio.run")
    def testexecute_mcp_request_connection_error(
        self, mock_asyncio_run, mock_make_client
    ):
        """Test MCP request with connection error."""
        mock_asyncio_run.side_effect = ConnectionError("Connection failed")

        with patch("persistproc.tools.CLI_LOGGER") as mock_logger:
            execute_mcp_request("test_tool", 8947)
            mock_logger.error.assert_called_with(
                "Cannot connect to persistproc server on port %d. Start it with 'persistproc serve'.",
                8947,
            )

    @patch("persistproc.mcp_client_utils.make_client")
    @patch("persistproc.tools.asyncio.run")
    def testexecute_mcp_request_error_response(
        self, mock_asyncio_run, mock_make_client
    ):
        """Test MCP request with error in response."""
        # Setup mock client that returns error
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.text = '{"error": "Process not found"}'
        mock_client.call_tool.return_value = [mock_result]
        mock_make_client.return_value.__aenter__.return_value = mock_client

        def run_coro(coro):
            import asyncio

            return asyncio.get_event_loop().run_until_complete(coro)

        mock_asyncio_run.side_effect = run_coro

        with (
            patch("builtins.print") as mock_print,
            patch("persistproc.tools.CLI_LOGGER") as mock_logger,
        ):
            execute_mcp_request("test_tool", 8947)

            # Verify error was logged and JSON was still printed
            mock_print.assert_called_once()
            mock_logger.error.assert_called_with("Process not found")


class TestStartProcessTool:
    """Test the StartProcessTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        # Create a mock process manager
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.start.return_value = mock_result

        result = StartProcessTool._apply(
            mock_manager,
            "python -m http.server",
            "/tmp",
            {"VAR": "value"},
            "web-server",
        )

        assert result == mock_result
        mock_manager.start.assert_called_once_with(
            command="python -m http.server",
            working_directory=Path("/tmp"),
            environment={"VAR": "value"},
            label="web-server",
        )

    def test_build_subparser(self):
        """Test CLI subparser configuration."""
        tool = StartProcessTool()
        mock_parser = MagicMock()

        tool.build_subparser(mock_parser)

        # Verify arguments were added
        assert mock_parser.add_argument.call_count >= 3
        call_args = [call[0] for call in mock_parser.add_argument.call_args_list]
        assert any("--working-directory" in args for args in call_args)
        assert any("--label" in args for args in call_args)
        assert any("command_" in args for args in call_args)

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args(self, mock_mcp_request):
        """Test CLI execution."""
        tool = StartProcessTool()
        args = Namespace(
            command_="python",
            args=["-m", "http.server"],
            working_directory="/tmp",
            label="test-label",
        )

        with patch.dict(os.environ, {"TEST_VAR": "value"}, clear=True):
            tool.call_with_args(args, 8947)

        mock_mcp_request.assert_called_once_with(
            "start",
            8947,
            {
                "command": "python -m http.server",
                "working_directory": "/tmp",
                "environment": {"TEST_VAR": "value"},
                "label": "test-label",
            },
            "json",
        )

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args_no_extra_args(self, mock_mcp_request):
        """Test CLI execution with single command."""
        tool = StartProcessTool()
        args = Namespace(command_="echo", args=[], working_directory="/tmp", label=None)

        with patch.dict(os.environ, {"TEST_VAR": "value"}, clear=True):
            tool.call_with_args(args, 8947)

        # Verify command is not shell-joined when no args
        mock_mcp_request.assert_called_once()
        call_args, call_kwargs = mock_mcp_request.call_args
        assert call_args[0] == "start"
        assert call_args[1] == 8947
        assert call_args[2]["command"] == "echo"


class TestListProcessesTool:
    """Test the ListProcessesTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.list.return_value = mock_result

        result = ListProcessesTool._apply(mock_manager)

        assert result == mock_result
        mock_manager.list.assert_called_once()

    def test_build_subparser(self):
        """Test CLI subparser configuration (no args)."""
        tool = ListProcessesTool()
        mock_parser = MagicMock()

        tool.build_subparser(mock_parser)

        # Should not add any arguments
        mock_parser.add_argument.assert_not_called()

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args(self, mock_mcp_request):
        """Test CLI execution."""
        tool = ListProcessesTool()
        args = Namespace()

        tool.call_with_args(args, 8947)

        mock_mcp_request.assert_called_once_with("list", 8947, format="json")


class TestGetProcessStatusTool:
    """Test the GetProcessStatusTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.get_status.return_value = mock_result

        result = GetProcessStatusTool._apply(
            mock_manager, pid=123, command_or_label="python", working_directory="/tmp"
        )

        assert result == mock_result
        mock_manager.get_status.assert_called_once_with(
            pid=123, command_or_label="python", working_directory=Path("/tmp")
        )

    @patch("persistproc.tools.execute_mcp_request")
    @patch("persistproc.tools._parse_target_to_pid_or_command_or_label")
    def test_call_with_args(self, mock_parse, mock_mcp_request):
        """Test CLI execution."""
        mock_parse.return_value = (123, None)

        tool = GetProcessStatusTool()
        args = Namespace(target="123", args=[], working_directory="/tmp")

        tool.call_with_args(args, 8947)

        mock_parse.assert_called_once_with("123", [])
        mock_mcp_request.assert_called_once_with(
            "status",
            8947,
            {"pid": 123, "command_or_label": None, "working_directory": "/tmp"},
            "json",
        )


class TestStopProcessTool:
    """Test the StopProcessTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.stop.return_value = mock_result

        result = StopProcessTool._apply(
            mock_manager,
            pid=123,
            command_or_label="python",
            working_directory="/tmp",
            force=True,
            label="test",
        )

        assert result == mock_result
        mock_manager.stop.assert_called_once_with(
            pid=123,
            command_or_label="python",
            working_directory=Path("/tmp"),
            force=True,
            label="test",
        )

    @patch("persistproc.tools.execute_mcp_request")
    @patch("persistproc.tools._parse_target_to_pid_or_command_or_label")
    def test_call_with_args(self, mock_parse, mock_mcp_request):
        """Test CLI execution."""
        mock_parse.return_value = (None, "python script.py")

        tool = StopProcessTool()
        args = Namespace(
            target="python",
            args=["script.py"],
            working_directory="/tmp",
            force=True,
            port=8947,
        )

        tool.call_with_args(args, 8947)

        mock_parse.assert_called_once_with("python", ["script.py"])
        mock_mcp_request.assert_called_once_with(
            "stop",
            8947,
            {
                "pid": None,
                "command_or_label": "python script.py",
                "working_directory": "/tmp",
                "force": True,
            },
            "json",
        )


class TestRestartProcessTool:
    """Test the RestartProcessTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.restart.return_value = mock_result

        result = RestartProcessTool._apply(
            mock_manager,
            pid=123,
            command_or_label="python",
            working_directory="/tmp",
            label="test",
        )

        assert result == mock_result
        mock_manager.restart.assert_called_once_with(
            pid=123,
            command_or_label="python",
            working_directory=Path("/tmp"),
            label="test",
        )


class TestGetProcessOutputTool:
    """Test the GetProcessOutputTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.get_output.return_value = mock_result

        from persistproc.process_types import StreamEnum

        result = GetProcessOutputTool._apply(
            mock_manager,
            stream=StreamEnum.stdout,
            lines=50,
            before_time="2024-01-01T10:00:00Z",
            since_time="2024-01-01T09:00:00Z",
            pid=123,
            command_or_label="python",
            working_directory="/tmp",
        )

        assert result == mock_result
        mock_manager.get_output.assert_called_once_with(
            pid=123,
            stream=StreamEnum.stdout,
            lines=50,
            before_time="2024-01-01T10:00:00Z",
            since_time="2024-01-01T09:00:00Z",
            command_or_label="python",
            working_directory=Path("/tmp"),
        )


class TestGetProcessLogPathsTool:
    """Test the GetProcessLogPathsTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.get_log_paths.return_value = mock_result

        result = GetProcessLogPathsTool._apply(
            mock_manager, pid=123, command_or_label="python", working_directory="/tmp"
        )

        assert result == mock_result
        mock_manager.get_log_paths.assert_called_once_with(
            pid=123, command_or_label="python", working_directory=Path("/tmp")
        )


class TestKillPersistprocTool:
    """Test the KillPersistprocTool class."""

    def test_apply_method(self):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = {"pid": 12345}
        mock_manager.kill_persistproc.return_value = mock_result

        result = KillPersistprocTool._apply(mock_manager)

        assert result == mock_result
        mock_manager.kill_persistproc.assert_called_once()


class TestToolCollection:
    """Test the overall tool collection."""

    def test_all_tool_classes_count(self):
        """Test that all expected tools are in the collection."""
        assert len(ALL_TOOL_CLASSES) == 8

        tool_names = [tool_cls().name for tool_cls in ALL_TOOL_CLASSES]
        expected_names = {
            "start",
            "list",
            "status",
            "stop",
            "restart",
            "output",
            "get_log_paths",
            "kill_persistproc",
        }
        assert set(tool_names) == expected_names

    def test_tool_names_are_unique(self):
        """Test that all tool names are unique."""
        tool_names = [tool_cls().name for tool_cls in ALL_TOOL_CLASSES]
        assert len(tool_names) == len(set(tool_names))
