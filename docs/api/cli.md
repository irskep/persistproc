# CLI Reference

The `persistproc` command-line interface provides direct access to process management functionality. This reference covers all available commands and options.

## Overview

```bash
persistproc [GLOBAL_OPTIONS] [COMMAND] [COMMAND_OPTIONS] [ARGS...]
```

## Global Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--help` | `-h` | Show help message | - |
| `--version` | `-V` | Show version information | - |
| `--verbose` | `-v` | Enable verbose output | False |
| `--quiet` | `-q` | Suppress non-error output | False |
| `--config` | `-c` | Configuration file path | Auto-detect |

## Server Management

### --serve

Start the persistproc server daemon.

```bash
persistproc --serve [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--host HOST` | Server bind address | `127.0.0.1` |
| `--port PORT` | Server port | `8947` |
| `--log-level LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `--data-dir PATH` | Data directory path | `~/.local/share/persistproc` |
| `--log-dir PATH` | Log directory path | `{data-dir}/logs` |
| `--daemon` | Run as daemon (background) | False |
| `--pid-file PATH` | PID file for daemon mode | `{data-dir}/server.pid` |

**Examples:**

```bash
# Basic server start
persistproc --serve

# Custom host and port
persistproc --serve --host 0.0.0.0 --port 9000

# Debug mode
persistproc --serve --log-level DEBUG

# Background daemon
persistproc --serve --daemon --pid-file /var/run/persistproc.pid
```

**Environment Variables:**

```bash
export PERSISTPROC_HOST=0.0.0.0
export PERSISTPROC_PORT=8947
export PERSISTPROC_LOG_LEVEL=INFO
export PERSISTPROC_DATA_DIR=/custom/path
```

### --stop-server

Stop the running persistproc server.

```bash
persistproc --stop-server [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Force kill if graceful stop fails | False |
| `--timeout SECONDS` | Timeout for graceful stop | 10 |

**Examples:**

```bash
# Graceful stop
persistproc --stop-server

# Force stop if hanging
persistproc --stop-server --force
```

## Process Management

### Default Behavior (Start and Tail)

When you provide a command without explicit flags, persistproc will:
1. Start the process if it's not already running
2. Tail the logs in real-time

```bash
persistproc COMMAND [ARGS...]
```

**Examples:**

```bash
# Start and tail npm dev server
persistproc npm run dev

# Start and tail with environment variables
NODE_ENV=development persistproc npm run dev

# Start and tail Python server
persistproc python manage.py runserver
```

**Behavior:**
- If process is already running, just tail logs
- Press `Ctrl+C` to stop tailing and get stop/detach prompt
- Process continues running in background after detaching

### --start

Start a process without tailing logs.

```bash
persistproc --start [OPTIONS] COMMAND [ARGS...]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--working-dir PATH` | Working directory | Current directory |
| `--env KEY=VALUE` | Environment variable (can be repeated) | - |
| `--name NAME` | Process name/label | Auto-generated |

**Examples:**

```bash
# Start process in background
persistproc --start npm run dev

# Start with custom working directory
persistproc --start --working-dir /path/to/project npm run dev

# Start with environment variables
persistproc --start --env NODE_ENV=development --env PORT=3000 npm run dev

# Start with custom name
persistproc --start --name "frontend-dev" npm run dev
```

### --stop

Stop a running process.

```bash
persistproc --stop PID [OPTIONS]
persistproc --stop --name NAME [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Use SIGKILL instead of SIGTERM | False |
| `--timeout SECONDS` | Timeout for graceful stop | 10 |
| `--name NAME` | Stop by process name | - |

**Examples:**

```bash
# Stop by PID
persistproc --stop 12345

# Force stop
persistproc --stop 12345 --force

# Stop by name
persistproc --stop --name "frontend-dev"

# Stop with custom timeout
persistproc --stop 12345 --timeout 30
```

### --restart

Restart a running process with the same parameters.

```bash
persistproc --restart PID [OPTIONS]
persistproc --restart --name NAME [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Force kill if graceful stop fails | False |
| `--name NAME` | Restart by process name | - |

**Examples:**

```bash
# Restart by PID
persistproc --restart 12345

# Restart by name
persistproc --restart --name "frontend-dev"

# Force restart
persistproc --restart 12345 --force
```

## Information Commands

### --list

List all managed processes.

```bash
persistproc --list [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--format FORMAT` | Output format: table, json, csv | `table` |
| `--status STATUS` | Filter by status | All |
| `--name PATTERN` | Filter by name pattern | All |

**Examples:**

```bash
# List all processes
persistproc --list

# JSON output
persistproc --list --format json

# Filter by status
persistproc --list --status running

# Filter by name pattern
persistproc --list --name "*dev*"
```

**Output Format:**

```
PID     STATUS    COMMAND              STARTED              CPU%   MEM(MB)
12345   running   npm run dev          2024-01-15 10:30:45  2.5    128
12346   stopped   python manage.py     2024-01-15 10:25:12  0.0    0
```

### --status

Get detailed status of a specific process.

```bash
persistproc --status PID
persistproc --status --name NAME
```

**Examples:**

```bash
# Status by PID
persistproc --status 12345

# Status by name
persistproc --status --name "frontend-dev"
```

### --logs

View process logs.

```bash
persistproc --logs PID [OPTIONS]
persistproc --logs --name NAME [OPTIONS]
persistproc --logs [OPTIONS]  # Server logs when no PID specified
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--stream STREAM` | Stream to show: stdout, stderr, both | `both` |
| `--lines LINES` | Number of recent lines | `50` |
| `--follow` | Follow logs in real-time | False |
| `--since TIME` | Show logs since timestamp | - |
| `--until TIME` | Show logs until timestamp | - |
| `--name NAME` | Show logs by process name | - |

**Examples:**

```bash
# Recent logs
persistproc --logs 12345

# Follow logs in real-time
persistproc --logs 12345 --follow

# Show last 100 lines
persistproc --logs 12345 --lines 100

# Show only stderr
persistproc --logs 12345 --stream stderr

# Show logs since specific time
persistproc --logs 12345 --since "2024-01-15T10:00:00"

# Server logs
persistproc --logs
```

**Time Formats:**
- ISO 8601: `2024-01-15T10:30:45Z`
- Relative: `10m`, `1h`, `2d` (minutes, hours, days ago)
- Human: `"2024-01-15 10:30:45"`

## Administrative Commands

### --health

Check server health and connectivity.

```bash
persistproc --health [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--detailed` | Show detailed health information | False |
| `--timeout SECONDS` | Connection timeout | 5 |

**Examples:**

```bash
# Basic health check
persistproc --health

# Detailed health information
persistproc --health --detailed
```

### --reset

Reset PersistProc state (stops all processes and clears data).

```bash
persistproc --reset [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Skip confirmation prompt | False |
| `--keep-logs` | Preserve log files | False |

**Examples:**

```bash
# Reset with confirmation
persistproc --reset

# Force reset without confirmation
persistproc --reset --force

# Reset but keep logs
persistproc --reset --keep-logs
```

### --cleanup

Clean up old logs and dead processes.

```bash
persistproc --cleanup [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--max-age DAYS` | Remove logs older than N days | `7` |
| `--dry-run` | Show what would be cleaned without doing it | False |

**Examples:**

```bash
# Clean up old files
persistproc --cleanup

# Clean logs older than 3 days
persistproc --cleanup --max-age 3

# See what would be cleaned
persistproc --cleanup --dry-run
```

## Configuration

### --config-show

Show current configuration.

```bash
persistproc --config-show [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--format FORMAT` | Output format: table, json, yaml | `table` |

### --config-set

Set configuration value.

```bash
persistproc --config-set KEY VALUE
```

**Examples:**

```bash
# Set default log level
persistproc --config-set log_level DEBUG

# Set default data directory
persistproc --config-set data_dir /custom/path
```

### --config-reset

Reset configuration to defaults.

```bash
persistproc --config-reset [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--force` | Skip confirmation prompt | False |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | Command line argument error |
| `3` | Server connection error |
| `4` | Process not found |
| `5` | Permission denied |
| `6` | Operation timeout |
| `130` | Interrupted by user (Ctrl+C) |

## Environment Variables

PersistProc respects these environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `PERSISTPROC_HOST` | Server host | `127.0.0.1` |
| `PERSISTPROC_PORT` | Server port | `8947` |
| `PERSISTPROC_LOG_LEVEL` | Log level | `INFO` |
| `PERSISTPROC_DATA_DIR` | Data directory | `~/.local/share/persistproc` |
| `PERSISTPROC_CONFIG_FILE` | Config file path | `{data_dir}/config.yaml` |
| `PERSISTPROC_TIMEOUT` | Default operation timeout | `30` |

## Configuration File

PersistProc can use a YAML configuration file:

```yaml
# ~/.local/share/persistproc/config.yaml
server:
  host: 127.0.0.1
  port: 8947
  log_level: INFO

paths:
  data_dir: ~/.local/share/persistproc
  log_dir: ~/.local/share/persistproc/logs

processes:
  default_timeout: 30
  max_processes: 20
  log_retention_days: 7

logging:
  max_log_size_mb: 100
  rotate_logs: true
```

## Advanced Usage

### Process Filters

Use patterns to filter processes:

```bash
# List all npm processes
persistproc --list --name "*npm*"

# List all running processes
persistproc --list --status running

# Stop all dev servers
for pid in $(persistproc --list --format json | jq -r '.processes[] | select(.command | contains("dev")) | .pid'); do
  persistproc --stop $pid
done
```

### Scripting Integration

PersistProc is designed to work well in scripts:

```bash
#!/bin/bash
# start-dev-env.sh

# Start all development services
echo "Starting development environment..."

# Start frontend
FRONTEND_PID=$(persistproc --start npm run dev:frontend --format json | jq -r '.pid')
echo "Frontend started with PID: $FRONTEND_PID"

# Start backend
BACKEND_PID=$(persistproc --start npm run dev:backend --format json | jq -r '.pid')
echo "Backend started with PID: $BACKEND_PID"

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 5

# Check status
persistproc --list --format table
```

### Log Analysis

Analyze logs programmatically:

```bash
# Check for errors in the last hour
persistproc --logs --since 1h --stream stderr | grep -i error

# Monitor for specific patterns
persistproc --logs --follow | grep -E "(error|warning|fail)"

# Export logs for analysis
persistproc --logs --since 1d --format json > today-logs.json
```

---

**Next**: Check out the [MCP Tools Reference](mcp-tools.md) for details on AI agent integration.