# MCP Tools Reference

PersistProc exposes its functionality through Model Context Protocol (MCP) tools. This reference documents all available tools, their parameters, and usage examples.

## Tool Overview

| Tool | Purpose | Parameters | Returns |
|------|---------|------------|---------|
| [`start_process`](#start_process) | Start a new process | `command`, `working_directory?`, `environment?` | Process info |
| [`stop_process`](#stop_process) | Stop a running process | `pid`, `force?` | Stop result |
| [`restart_process`](#restart_process) | Restart a process | `pid` | New process info |
| [`list_processes`](#list_processes) | List all processes | None | Process list |
| [`get_process_status`](#get_process_status) | Get process details | `pid` | Detailed status |
| [`get_process_output`](#get_process_output) | Retrieve process logs | `pid`, `stream`, `lines?`, `before_time?`, `since_time?` | Log output |
| [`get_process_log_paths`](#get_process_log_paths) | Get log file paths | `pid` | File paths |

## start_process

Start a new long-running process under PersistProc management.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | ✅ | The command to execute |
| `working_directory` | string | ❌ | Working directory for the process |
| `environment` | object | ❌ | Environment variables as key-value pairs |

### Returns

```json
{
  "pid": 12345,
  "command": "npm run dev",
  "working_directory": "/path/to/project",
  "environment": {"NODE_ENV": "development"},
  "status": "running",
  "start_time": "2024-01-15T10:30:45Z",
  "log_prefix": "12345"
}
```

### Examples

#### Basic Process Start

```json
{
  "tool": "start_process",
  "parameters": {
    "command": "npm run dev"
  }
}
```

#### With Working Directory

```json
{
  "tool": "start_process",
  "parameters": {
    "command": "python manage.py runserver",
    "working_directory": "/path/to/django/project"
  }
}
```

#### With Environment Variables

```json
{
  "tool": "start_process",
  "parameters": {
    "command": "npm run dev",
    "working_directory": "/path/to/project",
    "environment": {
      "NODE_ENV": "development",
      "PORT": "3000",
      "DEBUG": "*"
    }
  }
}
```

### Error Conditions

| Error | Cause | Solution |
|-------|-------|----------|
| `Command not found` | Executable doesn't exist | Check command spelling and PATH |
| `Permission denied` | Insufficient permissions | Check file permissions |
| `Working directory not found` | Directory doesn't exist | Verify path exists |
| `Process already running` | Same command already managed | Use different parameters or stop existing process |

## stop_process

Stop a running process by sending termination signals.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | ✅ | Process ID to stop |
| `force` | boolean | ❌ | Use SIGKILL instead of SIGTERM (default: false) |

### Returns

```json
{
  "pid": 12345,
  "status": "stopped",
  "exit_code": 0,
  "stop_time": "2024-01-15T10:35:22Z",
  "signal": "SIGTERM"
}
```

### Examples

#### Graceful Stop

```json
{
  "tool": "stop_process",
  "parameters": {
    "pid": 12345
  }
}
```

#### Force Kill

```json
{
  "tool": "stop_process",
  "parameters": {
    "pid": 12345,
    "force": true
  }
}
```

### Termination Process

1. **Graceful (default)**: Sends SIGTERM, waits up to 10 seconds
2. **Force**: Immediately sends SIGKILL
3. **Cleanup**: Removes process from management, closes log files

## restart_process

Restart a process with the same parameters it was originally started with.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | ✅ | Process ID to restart |

### Returns

```json
{
  "old_pid": 12345,
  "new_pid": 12346,
  "command": "npm run dev",
  "status": "running",
  "restart_time": "2024-01-15T10:40:15Z"
}
```

### Example

```json
{
  "tool": "restart_process",
  "parameters": {
    "pid": 12345
  }
}
```

### Restart Process

1. **Store original parameters** (command, working directory, environment)
2. **Stop the current process** gracefully
3. **Start new process** with same parameters
4. **Return new process information**

## list_processes

Get a list of all processes currently managed by PersistProc.

### Parameters

None.

### Returns

```json
{
  "processes": [
    {
      "pid": 12345,
      "command": "npm run dev",
      "status": "running",
      "start_time": "2024-01-15T10:30:45Z",
      "cpu_percent": 2.5,
      "memory_mb": 128
    },
    {
      "pid": 12346,
      "command": "python manage.py runserver",
      "status": "running",
      "start_time": "2024-01-15T10:32:10Z",
      "cpu_percent": 1.2,
      "memory_mb": 64
    }
  ],
  "total_count": 2,
  "running_count": 2,
  "stopped_count": 0
}
```

### Example

```json
{
  "tool": "list_processes",
  "parameters": {}
}
```

### Process Status Values

| Status | Description |
|--------|-------------|
| `starting` | Process is being launched |
| `running` | Process is active |
| `stopping` | Graceful shutdown in progress |
| `stopped` | Process exited normally |
| `killed` | Process was force-terminated |
| `failed` | Process crashed or failed to start |

## get_process_status

Get detailed status information for a specific process.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | ✅ | Process ID to query |

### Returns

```json
{
  "pid": 12345,
  "command": "npm run dev",
  "working_directory": "/path/to/project",
  "environment": {"NODE_ENV": "development"},
  "status": "running",
  "start_time": "2024-01-15T10:30:45Z",
  "uptime_seconds": 3600,
  "cpu_percent": 2.5,
  "memory_mb": 128,
  "log_prefix": "12345",
  "exit_code": null,
  "last_output": "Server running on http://localhost:3000"
}
```

### Example

```json
{
  "tool": "get_process_status",
  "parameters": {
    "pid": 12345
  }
}
```

## get_process_output

Retrieve captured output (logs) from a process.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | ✅ | Process ID (use 0 for server logs) |
| `stream` | string | ✅ | Output stream: "stdout", "stderr", or "both" |
| `lines` | integer | ❌ | Number of recent lines to retrieve |
| `before_time` | string | ❌ | ISO8601 timestamp - get logs before this time |
| `since_time` | string | ❌ | ISO8601 timestamp - get logs since this time |

### Returns

```json
{
  "pid": 12345,
  "stream": "stdout",
  "lines_requested": 50,
  "lines_returned": 42,
  "output": "2024-01-15 10:30:45 - Server starting...\n2024-01-15 10:30:46 - Listening on port 3000\n...",
  "truncated": false,
  "timestamp_range": {
    "start": "2024-01-15T10:30:45Z",
    "end": "2024-01-15T10:35:22Z"
  }
}
```

### Examples

#### Recent Lines

```json
{
  "tool": "get_process_output",
  "parameters": {
    "pid": 12345,
    "stream": "stdout",
    "lines": 50
  }
}
```

#### Time-based Query

```json
{
  "tool": "get_process_output",
  "parameters": {
    "pid": 12345,
    "stream": "stderr",
    "since_time": "2024-01-15T10:30:00Z"
  }
}
```

#### Combined Streams

```json
{
  "tool": "get_process_output",
  "parameters": {
    "pid": 12345,
    "stream": "both",
    "lines": 100
  }
}
```

#### Server Logs

```json
{
  "tool": "get_process_output",
  "parameters": {
    "pid": 0,
    "stream": "stdout",
    "lines": 20
  }
}
```

### Stream Types

| Stream | Description |
|--------|-------------|
| `stdout` | Standard output from the process |
| `stderr` | Standard error from the process |
| `both` | Interleaved stdout and stderr |

## get_process_log_paths

Get the file system paths to log files for a process.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pid` | integer | ✅ | Process ID to query |

### Returns

```json
{
  "stdout": "/home/user/.local/share/persistproc/logs/processes/12345_stdout.log",
  "stderr": "/home/user/.local/share/persistproc/logs/processes/12345_stderr.log",
  "combined": "/home/user/.local/share/persistproc/logs/processes/12345_combined.log"
}
```

### Example

```json
{
  "tool": "get_process_log_paths",
  "parameters": {
    "pid": 12345
  }
}
```

### Use Cases

- **External log analysis**: Use with tools like `grep`, `awk`, or log analyzers
- **Log rotation**: Backup or archive log files
- **Debugging**: Direct file access for detailed investigation
- **Monitoring**: Set up file watchers or log shipping

## Error Handling

All tools return structured error responses when operations fail:

```json
{
  "error": "Process with PID 99999 not found",
  "error_code": "PROCESS_NOT_FOUND",
  "timestamp": "2024-01-15T10:35:22Z"
}
```

### Common Error Codes

| Error Code | Description | Common Causes |
|------------|-------------|---------------|
| `PROCESS_NOT_FOUND` | PID doesn't exist | Process was never started or already cleaned up |
| `COMMAND_FAILED` | Process start failed | Invalid command, permissions, or dependencies |
| `OPERATION_TIMEOUT` | Operation took too long | System overload or unresponsive process |
| `PERMISSION_DENIED` | Insufficient permissions | File system or process permissions |
| `INVALID_PARAMETER` | Bad parameter value | Wrong type or format |

## Usage Patterns

### Pattern 1: Safe Process Management

Always check if a process is running before starting:

```python
# Check existing processes
processes = client.list_processes()

# Look for existing instance
existing = None
for proc in processes['processes']:
    if 'npm run dev' in proc['command']:
        existing = proc
        break

if existing:
    # Restart existing process
    result = client.restart_process(existing['pid'])
else:
    # Start new process
    result = client.start_process('npm run dev')
```

### Pattern 2: Log Analysis

Retrieve and analyze recent logs:

```python
# Get recent errors
logs = client.get_process_output(
    pid=12345,
    stream='stderr',
    lines=50
)

# Look for issues
if 'error' in logs['output'].lower():
    print("❌ Found errors in logs")
elif 'warning' in logs['output'].lower():
    print("⚠️ Found warnings in logs")
else:
    print("✅ No issues detected")
```

### Pattern 3: Health Monitoring

Continuously monitor process health:

```python
def monitor_health(client):
    processes = client.list_processes()
    
    for proc in processes['processes']:
        status = client.get_process_status(proc['pid'])
        
        if status['status'] != 'running':
            print(f"⚠️ Process {proc['pid']} is {status['status']}")
        
        if status['cpu_percent'] > 80:
            print(f"🔥 High CPU usage: {status['cpu_percent']}%")
        
        if status['memory_mb'] > 1024:
            print(f"💾 High memory usage: {status['memory_mb']}MB")
```

---

**Next**: Check out the [CLI Reference](cli.md) for command-line usage and examples.