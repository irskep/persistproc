import json
from unittest.mock import Mock, patch

import pytest

from persistproc.core import ProcessManager
from persistproc.tools import create_tools


@pytest.fixture
def tools_env(mock_mcp_server, temp_dir, no_monitor_thread):
    pm = ProcessManager(temp_dir)
    create_tools(mock_mcp_server, pm)
    return mock_mcp_server, pm


class TestProcessTools:
    def test_list_processes_empty(self, tools_env):
        app, _ = tools_env
        assert json.loads(app.tools["list_processes"]()) == []

    def test_start_process_invalid_directory(self, tools_env):
        app, _ = tools_env
        res = json.loads(
            app.tools["start_process"](command="echo hi", working_directory="/no/dir")
        )
        assert "error" in res and "does not exist" in res["error"]

    def test_get_process_log_paths_invalid_pid(self, tools_env):
        app, _ = tools_env
        res = json.loads(app.tools["get_process_log_paths"](pid=424242))
        assert "error" in res and "not found" in res["error"]

    def test_start_and_list_process_success(self, tools_env, mock_subprocess):
        app, pm = tools_env
        with patch.object(pm.log_manager, "start_logging"):
            payload = json.loads(app.tools["start_process"](command="echo hi"))
        pid = payload["pid"]
        assert payload["status"] == "running"
        listed = json.loads(app.tools["list_processes"]())
        assert any(p["pid"] == pid for p in listed)

    def test_restart_process_tool(self, tools_env):
        app, pm = tools_env
        first_proc = Mock(pid=10001, stdout=Mock(), stderr=Mock())
        second_proc = Mock(pid=10002, stdout=Mock(), stderr=Mock())
        with (
            patch(
                "persistproc.core.subprocess.Popen",
                side_effect=[first_proc, second_proc],
            ),
            patch.object(pm.log_manager, "start_logging"),
        ):
            start_info = json.loads(app.tools["start_process"](command="echo hi"))
            assert start_info["pid"] == 10001
            restart_info = json.loads(app.tools["restart_process"](pid=10001))
            assert restart_info["pid"] == 10002
            assert pm.processes[10001].status != "running"
            assert pm.processes[10002].status == "running"
