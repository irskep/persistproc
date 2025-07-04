import pytest
from unittest.mock import patch
from pathlib import Path
from argparse import Namespace
import subprocess
import sys

from persistproc.cli import (
    parse_cli,
    ServeAction,
    RunAction,
    ToolAction,
    get_default_port,
    get_default_data_dir,
)


@pytest.fixture
def mock_setup_logging():
    with patch(
        "persistproc.cli.setup_logging", return_value=Path("/fake/log/path")
    ) as mock:
        yield mock


def test_parse_cli_no_args(mock_setup_logging):
    """Test `persistproc` -> `serve` default."""
    action, log_path = parse_cli([])
    assert isinstance(action, ServeAction)
    assert action.port == get_default_port()
    assert action.data_dir == get_default_data_dir()
    assert action.verbose == 0
    assert log_path == Path("/fake/log/path")
    mock_setup_logging.assert_called_once()


def test_parse_cli_serve_command(mock_setup_logging):
    """Test `persistproc serve --port ...`."""
    action, _ = parse_cli(["serve", "--port", "1234", "-vv"])
    assert isinstance(action, ServeAction)
    assert action.port == 1234
    assert action.verbose == 2


def test_parse_cli_implicit_serve_with_flags(mock_setup_logging):
    """Test `persistproc --port ...` -> `serve`."""
    action, _ = parse_cli(["--port", "4321"])
    assert isinstance(action, ServeAction)
    assert action.port == 4321


def test_parse_cli_implicit_run(mock_setup_logging):
    """Test `persistproc my-script.py` -> `run`."""
    action, _ = parse_cli(["my-script.py", "arg1"])
    assert isinstance(action, RunAction)
    assert action.command == "my-script.py"
    assert action.run_args == ["arg1"]


def test_parse_cli_global_flags_before_subcommand(mock_setup_logging):
    """Global flags like -v and --port should be accepted before the subcommand."""
    action, _ = parse_cli(["-v", "serve", "--port", "12345"])
    assert isinstance(action, ServeAction)
    assert action.verbose == 1
    assert action.port == 12345


def test_parse_cli_explicit_run(mock_setup_logging):
    """Test `persistproc run ...`."""
    action, _ = parse_cli(["run", "python", "-m", "http.server"])
    assert isinstance(action, RunAction)
    assert action.command == "python"
    assert action.run_args == ["-m", "http.server"]


def test_parse_cli_run_with_quoted_string(mock_setup_logging):
    """Test `persistproc run \"echo 'hello world'\"`."""
    action, _ = parse_cli(["run", "echo 'hello world'"])
    assert isinstance(action, RunAction)
    assert action.command == "echo"
    assert action.run_args == ["hello world"]


def test_parse_cli_tool_command(mock_setup_logging):
    """Test `persistproc start_process ...`."""
    action, _ = parse_cli(["start_process", "sleep 10"])
    assert isinstance(action, ToolAction)
    assert isinstance(action.args, Namespace)
    assert action.args.command == "start_process"
    assert action.args.command_ == "sleep 10"


def test_parse_cli_tool_with_common_args(mock_setup_logging):
    """Test tool command with shared arguments like --port."""
    action, _ = parse_cli(["list_processes", "--port", "9999"])
    assert isinstance(action, ToolAction)
    assert action.args.port == 9999


def test_parse_cli_restart_process_by_pid(mock_setup_logging):
    """Test `persistproc restart_process 123`."""
    action, _ = parse_cli(["restart_process", "123"])
    assert isinstance(action, ToolAction)
    assert action.tool.name == "restart_process"
    assert action.args.command_or_pid == "123"
    assert not action.args.args


def test_parse_cli_restart_process_by_command(mock_setup_logging):
    """Test `persistproc restart_process sleep 10`."""
    action, _ = parse_cli(["restart_process", "sleep", "10"])
    assert isinstance(action, ToolAction)
    assert action.tool.name == "restart_process"
    assert action.args.command_or_pid == "sleep"
    assert action.args.args == ["10"]


def test_parse_cli_restart_process_by_command_and_cwd(mock_setup_logging):
    """Test `persistproc restart_process sleep 10 --working-directory /tmp`."""
    action, _ = parse_cli(
        ["restart_process", "sleep", "10", "--working-directory", "/tmp"]
    )
    assert isinstance(action, ToolAction)
    assert action.tool.name == "restart_process"
    assert action.args.command_or_pid == "sleep"
    assert action.args.args == ["10"]
    assert action.args.working_directory == "/tmp"


def test_parse_cli_data_dir_and_verbose_for_logging(mock_setup_logging):
    """Check that logging setup receives the correct arguments."""
    data_dir = Path("/custom/data")
    parse_cli(["serve", "--data-dir", str(data_dir), "-vvv"])
    mock_setup_logging.assert_called_with(3, data_dir)


def test_root_help_displays_subcommands():
    """`persistproc --help` lists available sub-commands (serve, run, etc.)."""
    cmd = [sys.executable, "-m", "persistproc", "--help"]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)

    # Exit code 0 and key sub-commands in help output.
    assert proc.returncode == 0, proc.stderr
    assert "serve" in proc.stdout
    assert "list-processes" in proc.stdout or "list_processes" in proc.stdout
