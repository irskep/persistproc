# persistproc

A shared process layer for multi-agent development workflows

[![PyPI version](https://badge.fury.io/py/persistproc.svg)](https://badge.fury.io/py/persistproc)
[![Test Coverage](./coverage.svg)](https://shields.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---


## What is `persistproc`?

Persistproc is an MCP server which lets agents and humans see and control long-running processes like web servers. The goal is to reduce the amount of copying and pasting you need to do, make it easier for you to use multiple agents, and be tool-agnostic.

There is no config file. Processes are managed entirely at runtime. This is not a replacement for supervisord.

### Example use case: basic web development

Suppose you're working on a todo list app, and it has a dev server you normally start with `npm run dev`. This server watches your code for changes, typechecks it, lints it, and hot-reloads the page. When there's an error, it prints the error to your terminal.

If you're working with an LLM agent such as Cursor or Claude Code, if you see an error, you might copy/paste it from your terminal to the agent and ask how to fix it. Then the agent might make some changes, and maybe you hit another error, so you copy/paste again, and the agent makes another change…etc.

If the agent could see the changes directly, you wouldn't need to do anything! With persistproc, that's possible. Instead of saying `npm run dev`, say `persistproc npm run dev`, and the agent can instantly read its output or even restart it. Otherwise, you can still see its output in your original terminal, and kill it with Ctrl+C, like your normally do.

### Example use case: complex web development

Suppose you need to run four processes to get your web app working locally. Maybe an API, frontend server, SCSS builder, and Postgres. Each service emits its own logs.

If you run into an error while testing locally, you can go read all four log files to find out what happened.

But if you started those processes with persistproc, then the agent can read everything at once and possibly give you a quicker diagnosis.

> [!NOTE]
> **Why not just use Cursor and let the agent open a terminal?**
>
> 1. Not everyone likes using the terminal in Cursor/VSCode. Engineers have many different workflows.
> 2. _Only_ Cursor's agents can see the process, not Claude Code, Gemini CLI, etc.

## Available Tools

`persistproc` exposes a standard [Model Context Protocol (MCP)](https://modelcontext.com/) server on `http://127.0.0.1:8947`. You can use any MCP-compatible client to interact with it programmatically.

The server exposes the following tools:

| Tool | Description |
| --- | --- |
| `start(command: str, working_directory: str = None, environment: dict = None)` | Start a new long-running process. |
| `list()` | List all managed processes and their status. |
| `get_status(pid: int)` | Get the detailed status of a specific process. |
| `stop(pid: int, command: str = None, working_directory: str = None, force: bool = False)` | Stop a running process by its PID. |
| `restart(pid: int, command: str = None, working_directory: str = None)` | Stops a process and starts it again with the same parameters. |
| `get_output(pid: int, stream: str, lines: int = None, before_time: str = None, since_time: str = None)` | Retrieve captured output from a process. |
| `get_log_paths(pid: int)` | Get the paths to the log files for a specific process. |
| `kill_persistproc()` | Kill all managed processes and get the PID of the persistproc server. |

## Getting started

### 1. Install `persistproc`

```bash
pip install persistproc
```

### 2. Start the server and configure your agent

Run this in a dedicated terminal and leave it running.

```bash
persistproc serve
```

The first thing `persistproc serve` outputs is configuration instructions for various agents, so follow those instructions if you haven't already.

### 3. Start a Process

In another terminal, `cd` to your project's directory and run your command via `persistproc`.

```bash
# Example: starting a Node.js development server
cd /path/to/your/project
persistproc npm run dev
```

The command is sent to the server, and its output is streamed to your terminal. You can safely close this terminal, and the process will continue to run.


> [!TIP]
> Or just ask your agent to "run your dev server using persistproc," and it will probably find the right command by looking at your `package.json` file and run it using `persistproc`.

With this, your agent can now use the available tools to manage your development environment.

## Example Agent Interaction

Once your agent is connected, you can ask it to manage your processes. Assuming you have started a web server with `persistproc npm run dev` (PID 12345), you can now interact with it.

*   **You**: "List the running processes."
    *   **Agent**: Calls `list()` and shows you the running `npm run dev` process.

*   **You**: "The web server seems stuck. Can you restart it?"
    *   **Agent**: Identifies the correct process and calls `restart(pid=12345)`.

*   **You**: "Show me any errors from the web server."
    *   **Agent**: Calls `get_output(pid=12345, stream="stderr")` to retrieve the latest error logs.

## Development

Run persistproc in a fully configured virtualenv with `./pp`. Run other commands such as `pytest` in a virtualenv with `./run-in-venv.sh`.

## License

This project is licensed under the MIT License. 