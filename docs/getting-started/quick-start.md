# Quick Start Guide

Get PersistProc running in your development environment in just a few minutes.

## Prerequisites

- Python 3.10 or higher
- Unix-like operating system (Linux, macOS)
- An AI agent that supports MCP (Model Context Protocol)

## Step 1: Installation

Install PersistProc from PyPI:

```bash
pip install persistproc
```

!!! tip "Virtual Environment Recommended"
    For best results, install PersistProc in a virtual environment:
    ```bash
    python -m venv persistproc-env
    source persistproc-env/bin/activate  # On Windows: persistproc-env\Scripts\activate
    pip install persistproc
    ```

## Step 2: Start the PersistProc Server

The PersistProc server is the central hub that manages all your processes. Start it in a dedicated terminal:

```bash
persistproc --serve
```

You should see output similar to:

```
2024-01-15 10:30:45 - INFO - Starting PersistProc server on http://127.0.0.1:8947
2024-01-15 10:30:45 - INFO - MCP endpoint available at http://127.0.0.1:8947/mcp/
2024-01-15 10:30:45 - INFO - Server ready for connections
```

!!! success "Server Running"
    Keep this terminal open! The PersistProc server needs to stay running to manage your processes.

## Step 3: Configure Your AI Agent

Now you need to tell your AI agent how to connect to PersistProc.

=== "Cursor/VS Code"

    1. Open your VS Code/Cursor settings (Cmd/Ctrl + ,)
    2. Search for "mcp"
    3. Add the following to your `settings.json`:

    ```json
    {
      "mcp.servers": {
        "persistproc": {
          "url": "http://127.0.0.1:8947/mcp/"
        }
      }
    }
    ```

    4. Restart your editor to apply the changes

=== "Claude Code"

    With the PersistProc server running, add it to Claude Code:

    ```bash
    claude mcp add --transport http persistproc http://127.0.0.1:8947/mcp/
    ```

    Verify the connection:
    ```bash
    claude mcp list
    ```

=== "Other MCP Clients"

    For other MCP-compatible tools, use the endpoint:
    ```
    http://127.0.0.1:8947/mcp/
    ```

## Step 4: Test Your Setup

Let's verify everything is working by testing the basic functionality.

### Via AI Agent

Ask your AI assistant:

> "List all running processes using PersistProc"

The agent should use the `list_processes` tool and return something like:

```json
{
  "processes": [],
  "total_count": 0
}
```

### Via Command Line

You can also test directly from your terminal:

```bash
# Start a simple process
persistproc echo "Hello, PersistProc!"

# List all processes
persistproc --list
```

## Step 5: Your First Managed Process

Now let's start a real development server. If you have a Node.js project:

### Option A: Via AI Agent

Ask your assistant:

> "Start the development server using npm run dev"

The agent will use the `start_process` tool to start your server.

### Option B: Via Command Line

```bash
# Start and tail the process
persistproc npm run dev

# Or just start without tailing
persistproc --start npm run dev
```

### Verify It's Working

Check that your process is running:

```bash
persistproc --list
```

You should see your process listed with its PID, status, and command.

## What's Next?

🎉 **Congratulations!** You now have PersistProc running and managing your development processes.

### Explore Key Features

- **Process Management**: Try restarting your server from a different tool
- **Log Access**: Ask your AI agent to show you recent logs
- **Multi-Process**: Start multiple services and see them all managed centrally

### Learn More

- [Core Concepts](../user-guide/core-concepts.md) - Understand how PersistProc works
- [Agent Integration](../user-guide/agent-integration.md) - Advanced AI agent configuration
- [Web Development Example](../examples/web-development.md) - Real-world usage patterns

### Common Next Steps

1. **Set up your main development server**: `persistproc npm run dev`
2. **Configure additional agents**: Set up PersistProc in all your development tools
3. **Explore workflows**: Try the [multi-agent workflows](../user-guide/workflows.md)

---

!!! question "Having Issues?"
    Check the [Troubleshooting Guide](../user-guide/troubleshooting.md) or [file an issue](https://github.com/irskep/persistproc-mcp/issues) on GitHub.