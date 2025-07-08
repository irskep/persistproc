"""Unit tests for tools.py using mocks/fakes to avoid real MCP calls."""

import asyncio
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from persistproc.process_manager import ProcessManager
from persistproc.tools import (
    ALL_TOOL_CLASSES,
    CtrlProcessTool,
    GetProcessOutputTool,
    ListProcessesTool,
    _parse_target_to_pid_or_command_or_label,
)
from persistproc.mcp_client_utils import execute_mcp_request
from persistproc.process_types import StreamEnum


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


class TestCtrlProcessTool:
    """Test the CtrlProcessTool class."""

    def test_apply_method_start(self, tmp_path):
        """Test the _apply static method for start action."""
        # Create a mock process manager
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.ctrl.return_value = mock_result

        result = CtrlProcessTool._apply(
            mock_manager,
            action="start",
            command_or_label="python -m http.server",
            working_directory=str(tmp_path),
            environment={"VAR": "value"},
            label="web-server",
        )

        assert result == mock_result
        mock_manager.ctrl.assert_called_once_with(
            action="start",
            pid=None,
            command_or_label="python -m http.server",
            working_directory=str(tmp_path),
            environment={"VAR": "value"},
            force=False,
            label="web-server",
        )

    def test_apply_method_stop(self):
        """Test the _apply static method for stop action."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.ctrl.return_value = mock_result

        result = CtrlProcessTool._apply(
            mock_manager,
            action="stop",
            pid=123,
            force=True,
        )

        assert result == mock_result
        mock_manager.ctrl.assert_called_once_with(
            action="stop",
            pid=123,
            command_or_label=None,
            working_directory=None,
            environment=None,
            force=True,
            label=None,
        )

    def test_build_subparser(self):
        """Test CLI subparser configuration."""
        tool = CtrlProcessTool()
        mock_parser = MagicMock()

        tool.build_subparser(mock_parser)

        # Verify arguments were added
        assert mock_parser.add_argument.call_count >= 6
        call_args = [call[0] for call in mock_parser.add_argument.call_args_list]
        assert any("--working-directory" in args for args in call_args)
        assert any("--environment" in args for args in call_args)
        assert any("--force" in args for args in call_args)
        assert any("--label" in args for args in call_args)
        assert any("action" in args for args in call_args)
        assert any("target" in args for args in call_args)

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args_ctrl_start(self, mock_mcp_request, tmp_path):
        """Test CLI execution for ctrl start."""
        tool = CtrlProcessTool()
        args = Namespace(
            action="start",
            target="python",
            args=["-m", "http.server"],
            working_directory=str(tmp_path),
            label="test-label",
            environment=None,
            force=False,
        )

        tool.call_with_args(args, 8947, "json")

        # Verify MCP request was made with correct parameters
        mock_mcp_request.assert_called_once_with(
            "ctrl",
            8947,
            {
                "action": "start",
                "pid": None,
                "command_or_label": "python -m http.server",
                "working_directory": str(tmp_path),
                "environment": None,
                "force": False,
                "label": "test-label",
            },
            "json",
        )

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args_ctrl_stop_by_pid(self, mock_mcp_request):
        """Test CLI execution for ctrl stop by PID."""
        tool = CtrlProcessTool()
        args = Namespace(
            action="stop",
            target="123",
            args=[],
            working_directory=None,
            force=True,
        )

        tool.call_with_args(args, 8947, "json")

        mock_mcp_request.assert_called_once_with(
            "ctrl",
            8947,
            {
                "action": "stop",
                "pid": 123,
                "command_or_label": None,
                "working_directory": None,
                "environment": None,
                "force": True,
                "label": None,
            },
            "json",
        )


class TestListProcessesTool:
    """Test the ListProcessesTool class."""

    def test_apply_method(self):
        """Test the _apply static method without filters."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.list.return_value = mock_result

        result = ListProcessesTool._apply(mock_manager)

        assert result == mock_result
        mock_manager.list.assert_called_once_with(
            pid=None, command_or_label=None, working_directory=None
        )

    def test_apply_method_with_filters(self, tmp_path):
        """Test the _apply static method with filters."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.list.return_value = mock_result

        result = ListProcessesTool._apply(
            mock_manager,
            pid=123,
            command_or_label="python",
            working_directory=str(tmp_path),
        )

        assert result == mock_result
        mock_manager.list.assert_called_once_with(
            pid=123, command_or_label="python", working_directory=str(tmp_path)
        )

    def test_build_subparser(self):
        """Test CLI subparser configuration with filtering options."""
        tool = ListProcessesTool()
        mock_parser = MagicMock()

        tool.build_subparser(mock_parser)

        # Should add filtering arguments
        assert mock_parser.add_argument.call_count == 3
        call_args = [call[0] for call in mock_parser.add_argument.call_args_list]
        assert any("--pid" in args for args in call_args)
        assert any("--command-or-label" in args for args in call_args)
        assert any("--working-directory" in args for args in call_args)

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args_no_filters(self, mock_mcp_request):
        """Test CLI execution without filters."""
        tool = ListProcessesTool()
        args = Namespace(pid=None, command_or_label=None, working_directory=None)

        tool.call_with_args(args, 8947)

        mock_mcp_request.assert_called_once_with("list", 8947, format="json")

    @patch("persistproc.tools.execute_mcp_request")
    def test_call_with_args_with_filters(self, mock_mcp_request, tmp_path):
        """Test CLI execution with filters."""
        tool = ListProcessesTool()
        args = Namespace(
            pid=123, command_or_label="python", working_directory=str(tmp_path)
        )

        tool.call_with_args(args, 8947)

        mock_mcp_request.assert_called_once_with(
            "list",
            8947,
            {
                "pid": 123,
                "command_or_label": "python",
                "working_directory": str(tmp_path),
            },
            "json",
        )


class TestGetProcessOutputTool:
    """Test the GetProcessOutputTool class."""

    def test_apply_method(self, tmp_path):
        """Test the _apply static method."""
        mock_manager = MagicMock(spec=ProcessManager)
        mock_result = MagicMock()
        mock_manager.get_output.return_value = mock_result

        result = GetProcessOutputTool._apply(
            mock_manager,
            stream=StreamEnum.stdout,
            lines=50,
            before_time="2024-01-01T10:00:00Z",
            since_time="2024-01-01T09:00:00Z",
            pid=123,
            command_or_label="python",
            working_directory=str(tmp_path),
        )

        assert result == mock_result
        mock_manager.get_output.assert_called_once_with(
            pid=123,
            stream=StreamEnum.stdout,
            lines=50,
            before_time="2024-01-01T10:00:00Z",
            since_time="2024-01-01T09:00:00Z",
            command_or_label="python",
            working_directory=Path(str(tmp_path)),
        )


class TestToolCollection:
    """Test the overall tool collection."""

    def test_all_tool_classes_count(self):
        """Test that all expected tools are in the collection."""
        assert len(ALL_TOOL_CLASSES) == 3

        tool_names = [tool_cls().name for tool_cls in ALL_TOOL_CLASSES]
        expected_names = {
            "ctrl",
            "list",
            "output",
        }
        assert set(tool_names) == expected_names

    def test_tool_names_are_unique(self):
        """Test that all tool names are unique."""
        tool_names = [tool_cls().name for tool_cls in ALL_TOOL_CLASSES]
        assert len(tool_names) == len(set(tool_names))
