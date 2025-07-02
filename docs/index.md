# PersistProc

## A shared process layer for the modern, multi-agent development workflow

[![PyPI version](https://badge.fury.io/py/persistproc.svg)](https://badge.fury.io/py/persistproc)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## The Problem We Solve

In the modern development landscape, you're likely using multiple AI agents and tools simultaneously. This creates a frustrating problem: **process isolation**.

=== "Before PersistProc"

    ```mermaid
    graph TD
        subgraph "Your Environment"
            A[iTerm] -- "runs" --> P1[Webpack Dev Server];
            B[Cursor] -- "tries to run (FAILS!)" --> P2[Webpack Dev Server];
            C[Claude Code] -- "asks you to restart manually" --> P3[Manual Intervention];
        end
        style P1 fill:#d4edda,stroke:#c3e6cb
        style P2 fill:#f8d7da,stroke:#f5c6cb
        style P3 fill:#fff3cd,stroke:#ffeaa7
    ```

    - Port conflicts when agents try to start the same service
    - Manual restarts breaking your development flow
    - No visibility into running processes across tools

=== "After PersistProc"

    ```mermaid
    graph TD
        subgraph "Your Agents"
            A[iTerm];
            B[Cursor];
            C[Claude Code];
        end

        subgraph "The PersistProc Hub"
            Hub(persistproc server);
            P1[Webpack Dev Server];
            P2[API Server];
            P3[Database];
            Hub -- manages --> P1;
            Hub -- manages --> P2;
            Hub -- manages --> P3;
        end
        
        A <--> Hub;
        B <--> Hub;
        C <--> Hub;

        subgraph "Benefits"
            R1["✅ Any agent can start, stop, restart processes"]
            R2["✅ No port conflicts"]
            R3["✅ Shared process visibility"]
            R4["✅ Persistent logs across sessions"]
        end
    ```

## Key Features

### 🤖 **Agent-First Design**
Built specifically for modern AI-assisted development workflows. Works seamlessly with Cursor, Claude Code, and any MCP-compatible tool.

### 🔄 **Process Persistence**
Your development servers survive terminal sessions, tool switches, and environment changes.

### 📊 **Centralized Management**
One hub to rule them all. Start, stop, restart, and monitor all your development processes from anywhere.

### 🔍 **Rich Observability**
Real-time logs, process status, and detailed output capture for all managed processes.

### 🌐 **Universal Access**
Access via CLI, MCP tools, or HTTP API. Your processes are available however you need them.

## Quick Start

Get up and running in 3 steps:

### 1. Install PersistProc

```bash
pip install persistproc
```

### 2. Start the Server

```bash
persistproc --serve
```

### 3. Configure Your AI Agent

=== "Cursor/VS Code"

    Add to your `settings.json`:
    ```json
    {
      "mcp.servers": {
        "persistproc": {
          "url": "http://127.0.0.1:8947/mcp/"
        }
      }
    }
    ```

=== "Claude Code"

    ```bash
    claude mcp add --transport http persistproc http://127.0.0.1:8947/mcp/
    ```

That's it! Now your AI agents can manage development processes collaboratively.

## Real-World Workflow Example

Here's how PersistProc transforms a typical web development session:

!!! example "Multi-Agent Web Development"

    **Scenario**: You're building a React app with multiple agents helping you.

    1. **Start Development** (in iTerm):
       ```bash
       persistproc npm run dev
       ```
       Your React dev server starts and logs stream to your terminal.

    2. **Make Changes** (in Cursor):
       Ask your AI assistant: *"The webpack config needs updating for the new CSS framework"*
       
       The assistant makes changes, then says: *"I'll restart the dev server for you"* and uses the `restart_process` tool.

    3. **Debug Issues** (in Claude Code):
       Ask: *"Check the dev server logs for any errors"*
       
       The assistant uses `get_process_output` to analyze recent logs and provides insights.

    4. **Add New Service** (anywhere):
       *"Start the API server too"* → `start_process(command="npm run api")`

    **Result**: Seamless collaboration between you and your AI agents, with zero manual process management.

## Why PersistProc?

### For Developers
- **Eliminate Context Switching**: Stop manually managing processes across different tools
- **Reduce Friction**: Let your AI agents handle the boring stuff
- **Improve Reliability**: No more "works on my machine" process issues

### For AI Agents
- **Better Tool Integration**: Standard MCP interface for process management
- **Shared State**: Consistent view of running processes across all agents
- **Rich Context**: Access to logs, status, and process history

### For Teams
- **Consistent Environments**: Same process management across all team members
- **Better Debugging**: Centralized logs and process monitoring
- **Simplified Onboarding**: One tool to manage all development processes

## What's Next?

- [**Quick Start Guide**](getting-started/quick-start.md) - Get running in 5 minutes
- [**Agent Integration**](user-guide/agent-integration.md) - Set up your favorite AI tools
- [**Web Development Example**](examples/web-development.md) - See it in action
- [**API Reference**](api/mcp-tools.md) - Explore all available tools

---

**Ready to supercharge your multi-agent development workflow?** [Get started now →](getting-started/quick-start.md)