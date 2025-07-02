# persistproc

A shared process layer for multi-agent development workflows

[![PyPI version](https://badge.fury.io/py/persistproc.svg)](https://badge.fury.io/py/persistproc)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What is `persistproc`?

When developing locally, you often need long-running processes like web servers, bundlers, or test watchers. Depending on where you start these processes, agents may or may not have access to them. If you start your web server from Cursor, then Claude Code can't see its output. If you prefer to run things in iTerm instead of the Cursor terminal, then Cursor's agents can't see or control the server process.

`persistproc` is an MCP server and command line tool which lets processes be started, inspected, and controlled from any terminal or agent. If you start your web server in iTerm, then Claude Code and Cursor can see its output and stop or restart it. An agent can also start a long-running process that you can then easily start watching the output of in your terminal.

Here's how it works:

1.  Run `persistproc --serve` once.
2.  Use an agent, or the `persistproc` command, to start your development tasks (e.g., `persistproc npm run dev`, or "Hey claude, run `npm run dev` using persistproc").
3.  Your AI agent, connected to the server, can now manage that process for you—restarting it after it makes a code change, or reading its logs to debug an issue—without needing to interrupt you or ask for terminal access. It doesn't matter if you or the agent started the process.

This creates a seamless workflow where the agent can autonomously manage the development environment in the background.

## Available Tools

`persistproc` exposes a standard [Model Context Protocol (MCP)](https://modelcontext.com/) server on `http://127.0.0.1:8947`. You can use any MCP-compatible client to interact with it programmatically.

The server exposes the following tools:

*   `start_process(command: str, working_directory: str = None, environment: dict = None)`: Start a new long-running process.
*   `list_processes()`: List all managed processes and their status.
*   `get_process_status(pid: int)`: Get the detailed status of a specific process.
*   `stop_process(pid: int, force: bool = False)`: Stop a running process by its PID.
*   `restart_process(pid: int)`: Stops a process and starts it again with the same parameters.
*   `get_process_output(pid: int, stream: str, lines: int = None, before_time: str = None, since_time: str = None)`: Retrieve captured output from a process.
*   `get_process_log_paths(pid: int)`: Get the paths to the log files for a specific process.

## Getting started

### 1. Install `persistproc`

```bash
pip install persistproc
```

### 2. Start the Server

Run this in a dedicated terminal and leave it running.

```bash
persistproc --serve
```

The server will log its own status to stdout and manage processes.

### 3. Configure Your AI Agent

To allow an AI agent to control these processes, configure its MCP client to point to the `persistproc` server.

#### Cursor (in `.cursor/mcp.json`)

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/"
    }
  }
}
```

#### Claude Code

```sh
claude mcp add --transport http persistproc http://127.0.0.1:8947/mcp/
```

### 2. Start a Process

In another terminal, `cd` to your project's directory and run your command via `persistproc`.

```bash
# Example: starting a Node.js development server
cd /path/to/your/project
persistproc npm run dev
```

The command is sent to the server, and its output is streamed to your terminal. You can safely close this terminal, and the process will continue to run.

Alternatively, just ask your agent to "run your dev server using persistproc," and it will probably find the right command by looking at your `package.json` file and run it using `persistproc`.

With this, your agent can now use the available tools to manage your development environment.

## Example Agent Interaction

Once your agent is connected, you can ask it to manage your processes. Assuming you have started a web server with `persistproc npm run dev` (PID 12345), you can now interact with it.

*   **You**: "List the running processes."
    *   **Agent**: Calls `list_processes()` and shows you the running `npm run dev` process.

*   **You**: "The web server seems stuck. Can you restart it?"
    *   **Agent**: Identifies the correct process and calls `restart_process(pid=12345)`.

*   **You**: "Show me any errors from the web server."
    *   **Agent**: Calls `get_process_output(pid=12345, stream="stderr")` to retrieve the latest error logs.

## Development

Use `./run-in-venv.sh` to install dependencies in a virtualenv and run `persistproc`.

## License

This project is licensed under the MIT License.