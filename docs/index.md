# persistproc

A persistent process management server for local development, designed to be controlled by AI agents.

[![PyPI version](https://badge.fury.io/py/persistproc.svg)](https://badge.fury.io/py/persistproc)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What is `persistproc`?

When developing locally, you often run multiple long-running processes like web servers, bundlers, or test watchers. Managing these across different terminals can be cumbersome, and it's difficult for external tools—like AI agents—to interact with them.

`persistproc` solves this by providing a central server to run and manage your development processes. You can start processes from your terminal, and they will continue to run in the background, managed by the server.

The primary way to interact with these processes is through a set of MCP tools. This allows AI agents (in editors like Cursor) to list, start, stop, restart, and view the logs of your development processes.

## Core Use Case

The main goal of `persistproc` is to create a stable layer of background processes that both you and your AI development assistants can see and control.

1.  You start the `persistproc` server once.
2.  You use the `persistproc` command to start your development tasks (e.g., `persistproc npm run dev`).
3.  Your AI agent, connected to the server, can now manage that process for you—restarting it after it makes a code change, or reading its logs to debug an issue—without needing to interrupt you or ask for terminal access.

This creates a seamless workflow where the agent can autonomously manage the development environment in the background.

## Core Functionality

*   **Process Server**: A single server (`persistproc --serve`) runs in the background and manages child processes.
*   **Client CLI**: A simple client (`persistproc <command>`) sends a command to the server and tails its logs to your terminal.
*   **Agent Tools (MCP)**: A suite of functions exposed over an HTTP endpoint for agents to manage processes. This includes:
    *   `start_process`
    *   `stop_process`
    *   `restart_process`
    *   `list_processes`
    *   `get_process_status`
    *   `get_process_output`
*   **Log Persistence**: stdout and stderr for each process are captured and stored in log files.

## Quick Start

### 1. Install `persistproc`

```bash
pip install persistproc
```

### 2. Start the Server

Run this in a dedicated terminal that you can leave running.

```bash
persistproc --serve
```

The server will log its own status to standard output and manage processes in the background.

### 3. Start a Process

In another terminal, `cd` to your project's directory and run your command via `persistproc`.

```bash
# Example: starting a Node.js development server
cd /path/to/your/project
persistproc npm run dev
```

The command is sent to the server, and its output is streamed to your terminal. You can safely close this terminal, and the process will continue to run.

### 4. Configure Your AI Agent

To allow an AI agent to control these processes, configure its MCP client to point to the `persistproc` server.

**Example: Cursor/VS Code `settings.json`**
```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/"
    }
  }
}
```

With this, your agent can now use the available tools to manage your development environment.

**Agent**: "Restart the dev server." -> `restart_process(pid=...)`
**Agent**: "Show me the latest errors." -> `get_process_output(pid=..., stream="stderr")`

## Example Agent Interaction

Once your agent is connected, you can ask it to manage your processes. Assuming you have started a web server with `persistproc npm run dev` (PID 12345), you can now interact with it.

*   **You**: "List the running processes."
    *   **Agent**: Calls `list_processes()` and shows you the running `npm run dev` process.

*   **You**: "The web server seems stuck. Can you restart it?"
    *   **Agent**: Identifies the correct process and calls `restart_process(pid=12345)`.

*   **You**: "Show me any errors from the web server."
    *   **Agent**: Calls `get_process_output(pid=12345, stream="stderr")` to retrieve the latest error logs.