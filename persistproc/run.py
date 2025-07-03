from __future__ import annotations

from typing import Sequence


def run(command: str, args: Sequence[str], verbose: int = 0) -> None:  # noqa: D401
    """
    Communicate with the persistproc server to ensure a command
    is running, and tail its stdout+stderr output on stdout.

    This is equivalent to:
    - persistproc start <command>, except if the command is already
      running, it gets left alone
    - get the combined log path for the running command
    - tail -f <combined log path>
    - on ctrl+c, depending on the value of --on-exit:
      - ask: y/n to stop the command or leave it running
      - stop
      - ignore
    """
    # TODO: instantiate an MCP client and use it to talk to the MCP server
    # which is already running via persistproc --serve.
    # implementing may require adding options to tools like start_process().
