# Agent Integration

PersistProc is designed from the ground up for AI agent integration. This guide covers how to set up and optimize PersistProc with various AI tools and agents.

## Supported Platforms

### ✅ Fully Supported

| Platform | Status | Setup Complexity | Features |
|----------|--------|------------------|----------|
| **Cursor** | ✅ Native | Easy | Full MCP support |
| **VS Code** | ✅ Via Extension | Easy | Full MCP support |
| **Claude Code** | ✅ Native | Easy | Full MCP support |
| **Custom MCP Clients** | ✅ Standard | Medium | Full API access |

### 🔄 In Development

| Platform | Status | ETA |
|----------|--------|-----|
| **GitHub Copilot** | 🔄 Planned | Q2 2024 |
| **JetBrains IDEs** | 🔄 Planned | Q3 2024 |

## Cursor Integration

Cursor has excellent MCP support, making it the easiest platform to integrate with PersistProc.

### Setup

1. **Start PersistProc Server**:
   ```bash
   persistproc --serve
   ```

2. **Configure Cursor**:
   Open settings (`Cmd/Ctrl + ,`) and add to `settings.json`:
   ```json
   {
     "mcp.servers": {
       "persistproc": {
         "url": "http://127.0.0.1:8947/mcp/"
       }
     }
   }
   ```

3. **Restart Cursor** to apply the configuration.

### Usage Patterns

#### Starting Development Servers

**Prompt**: *"Start the Next.js development server"*

**Agent Response**: The agent will use the `start_process` tool:
```json
{
  "tool": "start_process",
  "parameters": {
    "command": "npm run dev",
    "working_directory": "/path/to/project"
  }
}
```

#### Managing Multiple Services

**Prompt**: *"Start both the frontend and API servers"*

**Agent Actions**:
1. `start_process(command="npm run dev")` for frontend
2. `start_process(command="npm run api")` for backend
3. Reports both processes are running

#### Debugging with Logs

**Prompt**: *"Check the recent logs from the dev server for any errors"*

**Agent Response**: Uses `get_process_output` to retrieve and analyze logs.

### Advanced Configuration

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/",
      "timeout": 30000,
      "retries": 3,
      "description": "Process management for development servers"
    }
  },
  "mcp.enabledTools": {
    "persistproc": [
      "start_process",
      "stop_process", 
      "restart_process",
      "list_processes",
      "get_process_output"
    ]
  }
}
```

## VS Code Integration

VS Code requires the MCP extension for integration.

### Setup

1. **Install MCP Extension**:
   - Open Extensions panel
   - Search for "Model Context Protocol"
   - Install the official MCP extension

2. **Configure MCP Servers**:
   Add to your VS Code `settings.json`:
   ```json
   {
     "mcp.servers": {
       "persistproc": {
         "url": "http://127.0.0.1:8947/mcp/",
         "name": "PersistProc",
         "description": "Process management server"
       }
     }
   }
   ```

3. **Enable the Extension** and restart VS Code.

### Workspace-Specific Configuration

For project-specific setups, create `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/",
      "autoStart": true,
      "projectSpecific": true
    }
  },
  "persistproc.defaultCommands": {
    "dev": "npm run dev",
    "build": "npm run build",
    "test": "npm test"
  }
}
```

## Claude Code Integration

Claude Code has built-in MCP support, making integration straightforward.

### Setup

1. **Start PersistProc**:
   ```bash
   persistproc --serve
   ```

2. **Add to Claude Code**:
   ```bash
   claude mcp add --transport http persistproc http://127.0.0.1:8947/mcp/
   ```

3. **Verify Connection**:
   ```bash
   claude mcp list
   claude mcp test persistproc
   ```

### Usage Examples

#### Interactive Process Management

```bash
# Start a session with PersistProc available
claude chat

# In the chat, you can ask:
# "Start my development server"
# "Show me all running processes"
# "Restart the API server"
```

#### Automated Workflows

Create scripts that leverage Claude with PersistProc:

```bash
#!/bin/bash
# deploy.sh

# Ask Claude to manage the deployment process
claude chat --script "
Please use PersistProc to:
1. Stop the current dev server if running
2. Start the build process
3. Monitor the build logs
4. Start the production server when build completes
"
```

### Configuration Options

```bash
# Add with custom settings
claude mcp add \
  --transport http \
  --timeout 30 \
  --retries 3 \
  --description "Development process manager" \
  persistproc \
  http://127.0.0.1:8947/mcp/

# Set default working directory
claude config set persistproc.defaultWorkingDir /path/to/project

# Enable verbose logging
claude config set persistproc.verbose true
```

## Custom MCP Clients

For custom integrations, you can build your own MCP client.

### Python Example

```python
import requests
import json

class PersistProcClient:
    def __init__(self, base_url="http://127.0.0.1:8947"):
        self.base_url = base_url
        self.mcp_url = f"{base_url}/mcp/"
    
    def call_tool(self, tool_name, parameters=None):
        """Call a PersistProc MCP tool."""
        payload = {
            "tool": tool_name,
            "parameters": parameters or {}
        }
        
        response = requests.post(
            f"{self.mcp_url}/tools/{tool_name}",
            json=payload
        )
        
        return response.json()
    
    def start_process(self, command, working_dir=None, env=None):
        """Start a new process."""
        return self.call_tool("start_process", {
            "command": command,
            "working_directory": working_dir,
            "environment": env
        })
    
    def list_processes(self):
        """List all managed processes."""
        return self.call_tool("list_processes")
    
    def get_logs(self, pid, lines=50):
        """Get recent logs from a process."""
        return self.call_tool("get_process_output", {
            "pid": pid,
            "stream": "stdout",
            "lines": lines
        })

# Usage
client = PersistProcClient()

# Start a process
result = client.start_process("npm run dev")
print(f"Started process with PID: {result['pid']}")

# List all processes
processes = client.list_processes()
print(f"Running processes: {len(processes['processes'])}")
```

### JavaScript Example

```javascript
class PersistProcClient {
    constructor(baseUrl = 'http://127.0.0.1:8947') {
        this.baseUrl = baseUrl;
        this.mcpUrl = `${baseUrl}/mcp/`;
    }
    
    async callTool(toolName, parameters = {}) {
        const response = await fetch(`${this.mcpUrl}/tools/${toolName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tool: toolName,
                parameters: parameters
            })
        });
        
        return await response.json();
    }
    
    async startProcess(command, workingDir = null, env = null) {
        return await this.callTool('start_process', {
            command: command,
            working_directory: workingDir,
            environment: env
        });
    }
    
    async listProcesses() {
        return await this.callTool('list_processes');
    }
    
    async restartProcess(pid) {
        return await this.callTool('restart_process', { pid: pid });
    }
}

// Usage
const client = new PersistProcClient();

// Start a process
client.startProcess('npm run dev')
    .then(result => console.log(`Started PID: ${result.pid}`));
```

## Best Practices for Agents

### 1. Error Handling

Agents should handle PersistProc errors gracefully:

```python
def safe_start_process(client, command):
    try:
        result = client.start_process(command)
        if 'error' in result:
            return f"Failed to start process: {result['error']}"
        return f"Started process with PID {result['pid']}"
    except Exception as e:
        return f"Connection error: {e}"
```

### 2. Process Discovery

Before starting processes, check what's already running:

```python
def smart_start_process(client, command):
    # Check if similar process is already running
    processes = client.list_processes()
    
    for proc in processes.get('processes', []):
        if command in proc['command']:
            return f"Process already running (PID {proc['pid']})"
    
    # Start new process
    return client.start_process(command)
```

### 3. Log Analysis

Provide intelligent log analysis:

```python
def analyze_process_logs(client, pid):
    logs = client.get_logs(pid, lines=100)
    
    # Look for common patterns
    log_text = logs.get('output', '')
    
    if 'error' in log_text.lower():
        return "❌ Found errors in logs"
    elif 'warning' in log_text.lower():
        return "⚠️ Found warnings in logs"
    elif 'listening' in log_text.lower():
        return "✅ Server appears to be running"
    else:
        return "ℹ️ Process is running, check logs for details"
```

### 4. Context Awareness

Agents should understand the project context:

```python
def context_aware_start(client, project_type):
    commands = {
        'node': 'npm run dev',
        'python': 'python manage.py runserver',
        'rust': 'cargo run',
        'go': 'go run main.go'
    }
    
    command = commands.get(project_type)
    if command:
        return client.start_process(command)
    else:
        return "Unknown project type, please specify command"
```

## Troubleshooting Integration

### Common Issues

#### MCP Connection Failed

```bash
# Check if server is running
curl http://127.0.0.1:8947/health

# Check MCP endpoint
curl http://127.0.0.1:8947/mcp/

# Verify configuration
grep -A 5 "persistproc" ~/.config/cursor/settings.json
```

#### Tool Not Available

Ensure your agent has access to PersistProc tools:

```bash
# Test from command line
curl -X POST http://127.0.0.1:8947/mcp/tools/list_processes \
  -H "Content-Type: application/json" \
  -d '{"tool": "list_processes", "parameters": {}}'
```

#### Permission Errors

Check file permissions and user contexts:

```bash
# Check server logs
persistproc --logs

# Verify data directory permissions
ls -la ~/.local/share/persistproc/
```

### Debugging Tips

1. **Enable Debug Logging**:
   ```bash
   persistproc --serve --log-level DEBUG
   ```

2. **Test with CLI First**:
   ```bash
   persistproc echo "test"
   persistproc --list
   ```

3. **Verify Network Connectivity**:
   ```bash
   netstat -tulpn | grep 8947
   ```

---

**Next**: Explore [Workflows & Examples](workflows.md) to see PersistProc in action with real scenarios.