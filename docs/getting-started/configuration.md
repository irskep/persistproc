# Configuration

PersistProc provides flexible configuration options for both the server and client components. This guide covers all available settings and how to customize them for your environment.

## Server Configuration

### Default Settings

PersistProc starts with sensible defaults:

- **Host**: `127.0.0.1` (localhost only)
- **Port**: `8947`
- **Log Level**: `INFO`
- **Data Directory**: `~/.local/share/persistproc/` (Linux) or `~/Library/Application Support/persistproc/` (macOS)

### Command Line Options

Configure the server when starting:

```bash
# Basic server start
persistproc --serve

# Custom host and port
persistproc --serve --host 0.0.0.0 --port 9000

# Debug logging
persistproc --serve --log-level DEBUG

# Custom data directory
persistproc --serve --data-dir /custom/path
```

### Environment Variables

You can also use environment variables:

```bash
# Set default host and port
export PERSISTPROC_HOST=0.0.0.0
export PERSISTPROC_PORT=9000
export PERSISTPROC_LOG_LEVEL=DEBUG
export PERSISTPROC_DATA_DIR=/custom/path

# Start server with environment settings
persistproc --serve
```

### Configuration Precedence

Settings are applied in this order (highest precedence first):

1. Command line arguments
2. Environment variables
3. Default values

## MCP Client Configuration

### Cursor/VS Code

Add PersistProc to your editor's MCP configuration:

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/",
      "timeout": 30000,
      "retries": 3
    }
  }
}
```

**Advanced Configuration:**

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/",
      "timeout": 30000,
      "retries": 3,
      "headers": {
        "User-Agent": "Cursor/1.0"
      },
      "proxy": {
        "http": "http://proxy.example.com:8080",
        "https": "https://proxy.example.com:8080"
      }
    }
  }
}
```

### Claude Code

```bash
# Basic configuration
claude mcp add --transport http persistproc http://127.0.0.1:8947/mcp/

# With custom timeout
claude mcp add --transport http --timeout 30 persistproc http://127.0.0.1:8947/mcp/

# Verify configuration
claude mcp list
claude mcp test persistproc
```

### Custom MCP Clients

For custom integrations, use the standard MCP HTTP transport:

```python
import requests

# MCP endpoint
endpoint = "http://127.0.0.1:8947/mcp/"

# Example tool call
response = requests.post(f"{endpoint}/tools/list_processes", json={})
```

## Security Configuration

### Network Access

By default, PersistProc only accepts connections from localhost. To allow remote access:

!!! warning "Security Risk"
    Only enable remote access in trusted environments. PersistProc provides full process control.

```bash
# Allow connections from any IP
persistproc --serve --host 0.0.0.0

# Allow connections from specific network
persistproc --serve --host 192.168.1.100
```

### Authentication

!!! info "Coming Soon"
    Authentication features are planned for future releases.

Currently, PersistProc relies on network-level security. Consider:

- Running behind a VPN
- Using SSH tunneling
- Firewall restrictions

## Data Directory Structure

PersistProc stores data in a structured directory:

```
~/.local/share/persistproc/
├── logs/
│   ├── server.log
│   └── processes/
│       ├── 12345_stdout.log
│       ├── 12345_stderr.log
│       └── ...
├── state/
│   └── processes.json
└── config/
    └── server.conf
```

### Log Management

Configure log retention and rotation:

```bash
# Set log retention (days)
export PERSISTPROC_LOG_RETENTION=7

# Set max log file size (MB)
export PERSISTPROC_MAX_LOG_SIZE=100

# Disable log rotation
export PERSISTPROC_ROTATE_LOGS=false
```

### Custom Log Directory

```bash
# Use custom log directory
persistproc --serve --log-dir /var/log/persistproc
```

## Process Configuration

### Default Process Settings

```bash
# Set default working directory for new processes
export PERSISTPROC_DEFAULT_CWD=/path/to/project

# Set default environment variables for processes
export PERSISTPROC_DEFAULT_ENV='{"NODE_ENV":"development","DEBUG":"*"}'

# Set process timeout (seconds)
export PERSISTPROC_PROCESS_TIMEOUT=300
```

### Resource Limits

Configure resource limits for managed processes:

```bash
# Memory limit per process (MB)
export PERSISTPROC_MEMORY_LIMIT=1024

# CPU limit per process (percentage)
export PERSISTPROC_CPU_LIMIT=50

# Maximum number of processes
export PERSISTPROC_MAX_PROCESSES=10
```

## Advanced Configuration

### Custom Server Script

Create a custom startup script:

```bash
#!/bin/bash
# persistproc-server.sh

# Set environment
export PERSISTPROC_HOST=0.0.0.0
export PERSISTPROC_PORT=8947
export PERSISTPROC_LOG_LEVEL=INFO
export PERSISTPROC_DATA_DIR=/opt/persistproc

# Start server
exec persistproc --serve
```

### Systemd Service

Run PersistProc as a system service:

```ini
# /etc/systemd/system/persistproc.service
[Unit]
Description=PersistProc Process Manager
After=network.target

[Service]
Type=simple
User=persistproc
Group=persistproc
WorkingDirectory=/opt/persistproc
Environment=PERSISTPROC_HOST=127.0.0.1
Environment=PERSISTPROC_PORT=8947
Environment=PERSISTPROC_DATA_DIR=/var/lib/persistproc
ExecStart=/usr/local/bin/persistproc --serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable persistproc
sudo systemctl start persistproc
sudo systemctl status persistproc
```

### Docker Configuration

Example Docker Compose configuration:

```yaml
# docker-compose.yml
version: '3.8'

services:
  persistproc:
    image: python:3.11-slim
    command: >
      sh -c "pip install persistproc &&
             persistproc --serve --host 0.0.0.0"
    ports:
      - "8947:8947"
    environment:
      - PERSISTPROC_LOG_LEVEL=INFO
      - PERSISTPROC_DATA_DIR=/data
    volumes:
      - persistproc_data:/data
    restart: unless-stopped

volumes:
  persistproc_data:
```

## Configuration Validation

Verify your configuration:

```bash
# Test server connectivity
curl http://127.0.0.1:8947/health

# Test MCP endpoint
curl http://127.0.0.1:8947/mcp/

# Check server logs
persistproc --logs

# Validate configuration
persistproc --validate-config
```

## Troubleshooting Configuration

### Common Issues

#### Port Conflicts
```bash
# Find what's using the port
lsof -i :8947
netstat -tulpn | grep 8947

# Use a different port
persistproc --serve --port 9000
```

#### Permission Issues
```bash
# Fix data directory permissions
chmod 755 ~/.local/share/persistproc
chown -R $USER:$USER ~/.local/share/persistproc
```

#### Network Issues
```bash
# Test network connectivity
ping 127.0.0.1
telnet 127.0.0.1 8947
```

### Configuration Reset

Reset to defaults:

```bash
# Remove configuration
rm -rf ~/.local/share/persistproc/config/

# Clear environment variables
unset PERSISTPROC_HOST PERSISTPROC_PORT PERSISTPROC_LOG_LEVEL

# Restart server
persistproc --serve
```

---

**Next**: Learn about [Core Concepts](../user-guide/core-concepts.md) to understand how PersistProc works internally.