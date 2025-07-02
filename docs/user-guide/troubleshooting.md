# Troubleshooting Guide

This guide covers common issues you might encounter with PersistProc and how to resolve them.

## Quick Diagnostics

Start with these basic checks when something isn't working:

```bash
# Check if PersistProc server is running
curl -s http://127.0.0.1:8947/health || echo "Server not responding"

# Check server logs
persistproc --logs

# List running processes
persistproc --list

# Test basic functionality
persistproc echo "test"
```

## Installation Issues

### Python Version Error

**Symptoms**: Installation fails with Python version error
```
ERROR: Package 'persistproc' requires a different Python: 3.9.0 not in '>=3.10'
```

**Solutions**:

1. **Check your Python version**:
   ```bash
   python --version
   python3 --version
   ```

2. **Install Python 3.10+**:
   ```bash
   # Ubuntu/Debian
   sudo apt update && sudo apt install python3.10 python3.10-pip
   
   # macOS with Homebrew
   brew install python@3.10
   
   # Using pyenv
   pyenv install 3.10.0
   pyenv global 3.10.0
   ```

3. **Use specific Python version**:
   ```bash
   python3.10 -m pip install persistproc
   ```

### Permission Denied

**Symptoms**: Cannot install or create directories
```
ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied
```

**Solutions**:

1. **Use virtual environment** (recommended):
   ```bash
   python -m venv persistproc-env
   source persistproc-env/bin/activate
   pip install persistproc
   ```

2. **Install for user only**:
   ```bash
   pip install --user persistproc
   ```

3. **Fix permissions**:
   ```bash
   sudo chown -R $USER:$USER ~/.local/
   ```

### Module Not Found

**Symptoms**: ImportError or ModuleNotFoundError
```
ModuleNotFoundError: No module named 'persistproc'
```

**Solutions**:

1. **Verify installation**:
   ```bash
   pip list | grep persistproc
   which persistproc
   ```

2. **Reinstall**:
   ```bash
   pip uninstall persistproc
   pip install persistproc
   ```

3. **Check virtual environment**:
   ```bash
   which python
   pip show persistproc
   ```

## Server Issues

### Server Won't Start

**Symptoms**: Server fails to start or exits immediately

**Common Causes & Solutions**:

#### Port Already in Use
```bash
# Find what's using port 8947
lsof -i :8947
netstat -tulpn | grep 8947

# Kill conflicting process
kill <PID>

# Or use different port
persistproc --serve --port 9000
```

#### Permission Issues
```bash
# Check data directory permissions
ls -la ~/.local/share/persistproc/

# Fix permissions
chmod 755 ~/.local/share/persistproc/
chown -R $USER:$USER ~/.local/share/persistproc/
```

#### Missing Dependencies
```bash
# Check for missing dependencies
pip check

# Reinstall with dependencies
pip install --upgrade --force-reinstall persistproc
```

### Server Crashes

**Symptoms**: Server starts but crashes or becomes unresponsive

**Debugging Steps**:

1. **Check server logs**:
   ```bash
   persistproc --logs
   # or
   tail -f ~/.local/share/persistproc/logs/server.log
   ```

2. **Start with debug logging**:
   ```bash
   persistproc --serve --log-level DEBUG
   ```

3. **Check system resources**:
   ```bash
   df -h  # Disk space
   free -m  # Memory
   top  # CPU usage
   ```

4. **Verify network connectivity**:
   ```bash
   telnet 127.0.0.1 8947
   ping 127.0.0.1
   ```

### Memory Issues

**Symptoms**: High memory usage or out-of-memory errors

**Solutions**:

1. **Monitor memory usage**:
   ```bash
   # Check server memory usage
   ps aux | grep persistproc
   
   # Check managed processes
   persistproc --list
   ```

2. **Configure log retention**:
   ```bash
   export PERSISTPROC_LOG_RETENTION=3  # Keep logs for 3 days
   export PERSISTPROC_MAX_LOG_SIZE=50  # Max 50MB per log file
   ```

3. **Clean up old logs**:
   ```bash
   find ~/.local/share/persistproc/logs/ -name "*.log" -mtime +7 -delete
   ```

## Process Management Issues

### Process Won't Start

**Symptoms**: `start_process` fails or process exits immediately

**Common Causes**:

#### Command Not Found
```bash
# Check if command exists
which npm
which python
which node

# Verify PATH
echo $PATH

# Use full path
persistproc /usr/bin/node server.js
```

#### Working Directory Issues
```bash
# Check if directory exists
ls -la /path/to/project

# Use absolute path
persistproc --start --working-dir /absolute/path/to/project npm run dev
```

#### Environment Variables
```bash
# Check required environment variables
env | grep NODE
env | grep PATH

# Set environment variables
NODE_ENV=development persistproc npm run dev
```

#### Port Conflicts
```bash
# Check what's using the port
lsof -i :3000

# Use different port
PORT=3001 persistproc npm run dev
```

### Process Crashes

**Symptoms**: Process starts but exits unexpectedly

**Debugging Steps**:

1. **Check process logs**:
   ```bash
   # Get recent error output
   persistproc --logs <pid>
   
   # Or use MCP tool
   # get_process_output(pid=<pid>, stream="stderr", lines=50)
   ```

2. **Check exit code**:
   ```bash
   # Get detailed process status
   persistproc --status <pid>
   ```

3. **Test manually**:
   ```bash
   # Try running command directly
   cd /path/to/project
   npm run dev
   ```

4. **Check dependencies**:
   ```bash
   # Verify all dependencies are installed
   npm install
   pip install -r requirements.txt
   ```

### Process Becomes Unresponsive

**Symptoms**: Process appears running but doesn't respond

**Solutions**:

1. **Check process status**:
   ```bash
   ps aux | grep <pid>
   top -p <pid>
   ```

2. **Force restart**:
   ```bash
   persistproc --restart --force <pid>
   ```

3. **Check resource usage**:
   ```bash
   # Memory usage
   pmap <pid>
   
   # File descriptors
   lsof -p <pid>
   
   # System calls
   strace -p <pid>
   ```

## Agent Integration Issues

### MCP Connection Failed

**Symptoms**: AI agent can't connect to PersistProc

**Solutions**:

1. **Verify server is running**:
   ```bash
   curl http://127.0.0.1:8947/health
   ```

2. **Check MCP endpoint**:
   ```bash
   curl http://127.0.0.1:8947/mcp/
   ```

3. **Verify agent configuration**:
   ```bash
   # Cursor/VS Code - check settings.json
   grep -A 5 "persistproc" ~/.config/cursor/settings.json
   
   # Claude Code - list MCP servers
   claude mcp list
   ```

4. **Test MCP tools**:
   ```bash
   curl -X POST http://127.0.0.1:8947/mcp/tools/list_processes \
     -H "Content-Type: application/json" \
     -d '{"tool": "list_processes", "parameters": {}}'
   ```

### Tools Not Available

**Symptoms**: Agent reports "tool not found" or similar errors

**Solutions**:

1. **Check available tools**:
   ```bash
   curl http://127.0.0.1:8947/mcp/tools
   ```

2. **Restart agent**:
   - Cursor/VS Code: Restart editor
   - Claude Code: `claude mcp reload`

3. **Verify tool permissions**:
   ```json
   {
     "mcp.enabledTools": {
       "persistproc": [
         "start_process",
         "stop_process",
         "list_processes"
       ]
     }
   }
   ```

### Slow Response Times

**Symptoms**: Tools take a long time to respond

**Solutions**:

1. **Check server performance**:
   ```bash
   top -p $(pgrep persistproc)
   ```

2. **Reduce log verbosity**:
   ```bash
   persistproc --serve --log-level WARNING
   ```

3. **Increase timeout**:
   ```json
   {
     "mcp.servers": {
       "persistproc": {
         "url": "http://127.0.0.1:8947/mcp/",
         "timeout": 60000
       }
     }
   }
   ```

## Log and Data Issues

### Missing Logs

**Symptoms**: No output from `get_process_output` or log files

**Solutions**:

1. **Check log directory**:
   ```bash
   ls -la ~/.local/share/persistproc/logs/processes/
   ```

2. **Verify process is running**:
   ```bash
   persistproc --list
   ```

3. **Check log capture**:
   ```bash
   # Start a test process
   persistproc echo "test output"
   
   # Check if logs appear
   persistproc --logs <pid>
   ```

4. **Restart with clean logs**:
   ```bash
   # Stop server
   pkill persistproc
   
   # Clean old logs
   rm -rf ~/.local/share/persistproc/logs/
   
   # Restart server
   persistproc --serve
   ```

### Disk Space Issues

**Symptoms**: Logs fill up disk space

**Solutions**:

1. **Check disk usage**:
   ```bash
   du -sh ~/.local/share/persistproc/
   df -h ~/.local/share/persistproc/
   ```

2. **Configure log rotation**:
   ```bash
   export PERSISTPROC_MAX_LOG_SIZE=100  # 100MB per file
   export PERSISTPROC_LOG_RETENTION=7   # 7 days
   ```

3. **Manual cleanup**:
   ```bash
   # Remove old logs
   find ~/.local/share/persistproc/logs/ -name "*.log" -mtime +7 -delete
   
   # Compress large logs
   gzip ~/.local/share/persistproc/logs/processes/*.log
   ```

### Corrupted State

**Symptoms**: Inconsistent process states or weird behavior

**Solutions**:

1. **Reset state**:
   ```bash
   # Stop server
   pkill persistproc
   
   # Remove state files
   rm -rf ~/.local/share/persistproc/state/
   
   # Restart server
   persistproc --serve
   ```

2. **Manual cleanup**:
   ```bash
   # Kill all managed processes
   pkill -f "npm run dev"
   pkill -f "python manage.py"
   
   # Reset PersistProc
   persistproc --reset
   ```

## Performance Issues

### High CPU Usage

**Symptoms**: PersistProc server uses excessive CPU

**Solutions**:

1. **Check process count**:
   ```bash
   persistproc --list | wc -l
   ```

2. **Reduce log verbosity**:
   ```bash
   export PERSISTPROC_LOG_LEVEL=WARNING
   ```

3. **Monitor specific processes**:
   ```bash
   # Find CPU-hungry processes
   persistproc --list | grep -E "(running|cpu)"
   ```

4. **Limit concurrent processes**:
   ```bash
   export PERSISTPROC_MAX_PROCESSES=5
   ```

### Network Latency

**Symptoms**: Slow MCP responses from remote connections

**Solutions**:

1. **Use local connection**:
   ```bash
   # Ensure using localhost
   curl http://127.0.0.1:8947/health
   ```

2. **Check network interface**:
   ```bash
   netstat -tulpn | grep 8947
   ```

3. **Optimize timeouts**:
   ```json
   {
     "mcp.servers": {
       "persistproc": {
         "timeout": 10000,
         "retries": 1
       }
     }
   }
   ```

## Getting Help

If you can't resolve your issue:

### 1. Gather Information

```bash
# System information
uname -a
python --version
pip show persistproc

# PersistProc status
persistproc --version
curl -s http://127.0.0.1:8947/health

# Error logs
persistproc --logs | tail -50
```

### 2. Check Documentation

- [Installation Guide](../getting-started/installation.md)
- [Configuration Reference](../getting-started/configuration.md)
- [API Documentation](../api/mcp-tools.md)

### 3. Search Issues

- [GitHub Issues](https://github.com/irskep/persistproc-mcp/issues)
- [Discussions](https://github.com/irskep/persistproc-mcp/discussions)

### 4. File a Bug Report

Include:
- Operating system and version
- Python version
- PersistProc version
- Full error message
- Steps to reproduce
- Relevant log files

**Template**:
```markdown
## Environment
- OS: [Ubuntu 22.04 / macOS 13.0 / etc.]
- Python: [3.10.5]
- PersistProc: [0.1.0]

## Problem
[Brief description]

## Steps to Reproduce
1. [First step]
2. [Second step]
3. [Error occurs]

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Logs
```
[Paste relevant logs here]
```

## Additional Context
[Any other relevant information]
```

---

**Still having trouble?** Check our [GitHub Issues](https://github.com/irskep/persistproc-mcp/issues) or [start a discussion](https://github.com/irskep/persistproc-mcp/discussions).