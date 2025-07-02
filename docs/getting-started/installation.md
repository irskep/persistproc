# Installation

persistproc is a Python package that provides process management for multi-agent development workflows. This guide covers all installation methods and system requirements.

## System Requirements

### Operating System
- **Linux** (Ubuntu 18.04+, CentOS 7+, or equivalent)
- **macOS** (10.14+)
- **Unix-like systems**

!!! warning "Windows Support"
    persistproc is currently Unix-only. Windows support via WSL2 may work but is not officially tested.

### Python
- **Python 3.10 or higher**
- Virtual environment support (recommended)

### Dependencies
- `fastmcp==2.9.2` (automatically installed)

## Installation Methods

### Method 1: PyPI (Recommended)

The simplest way to install persistproc:

```bash
pip install persistproc
```

### Method 2: Virtual Environment (Best Practice)

For isolation and better dependency management:

```bash
# Create a virtual environment
python -m venv persistproc-env

# Activate it
source persistproc-env/bin/activate  # Linux/macOS
# persistproc-env\Scripts\activate    # Windows (if supported)

# Install persistproc
pip install persistproc
```

### Method 3: Development Installation

If you want to contribute or use the latest development version:

```bash
# Clone the repository
git clone https://github.com/irskep/persistproc-mcp.git
cd persistproc-mcp

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Method 4: System-wide Installation

!!! warning "Not Recommended"
    System-wide installation can conflict with other Python packages.

```bash
sudo pip install persistproc  # Not recommended
```

## Post-Installation Setup

### Verify Installation

Check that persistproc is installed correctly:

```bash
persistproc --version
```

You should see output like:
```
persistproc 0.1.0
```

### Test Basic Functionality

```bash
# Start the server (in one terminal)
persistproc --serve

# Test from another terminal
persistproc echo "Installation test successful!"
```

## Installation for Specific Use Cases

### For AI Agent Development

If you're building tools that integrate with persistproc:

```bash
pip install persistproc[dev]
```

This includes additional testing and development dependencies.

### For Production Environments

For production deployments:

```bash
pip install persistproc
```

Consider using Docker or system package managers for production.

### For Multiple Python Versions

If you manage multiple Python versions:

```bash
# Using specific Python version
python3.11 -m pip install persistproc

# Using pyenv
pyenv exec pip install persistproc
```

## Docker Installation

You can also run persistproc in a Docker container:

```dockerfile
FROM python:3.11-slim

# Install persistproc
RUN pip install persistproc

# Expose the default port
EXPOSE 8947

# Start the server
CMD ["persistproc", "--serve"]
```

Build and run:

```bash
docker build -t persistproc .
docker run -p 8947:8947 persistproc
```

## Package Managers

### Homebrew (macOS)

!!! info "Coming Soon"
    Homebrew formula is planned for a future release.

### APT/YUM (Linux)

!!! info "Coming Soon"
    System packages for major Linux distributions are planned.

## Troubleshooting Installation

### Common Issues

#### Python Version Error
```
ERROR: Package 'persistproc' requires a different Python: 3.9.0 not in '>=3.10'
```

**Solution**: Upgrade to Python 3.10 or higher:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3.10

# macOS with Homebrew
brew install python@3.10

# Or use pyenv
pyenv install 3.10.0
pyenv global 3.10.0
```

#### Permission Denied
```
ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied
```

**Solution**: Use a virtual environment instead of system-wide installation.

#### Missing Dependencies
```
ModuleNotFoundError: No module named 'fastmcp'
```

**Solution**: Reinstall PersistProc:
```bash
pip uninstall persistproc
pip install persistproc
```

#### Port Already in Use
```
ERROR: Address already in use: 127.0.0.1:8947
```

**Solution**: Check if another PersistProc instance is running:
```bash
# Find the process
lsof -i :8947

# Kill it if needed
kill <PID>
```

### Getting Help

If you encounter issues:

1. Check the [Troubleshooting Guide](../user-guide/troubleshooting.md)
2. Search [existing issues](https://github.com/irskep/persistproc-mcp/issues)
3. [File a new issue](https://github.com/irskep/persistproc-mcp/issues/new) with:
   - Your operating system and version
   - Python version (`python --version`)
   - Full error message
   - Steps to reproduce

## Updating PersistProc

### Upgrade to Latest Version

```bash
pip install --upgrade persistproc
```

### Check for Updates

```bash
pip list --outdated | grep persistproc
```

### Version History

See the [GitHub releases](https://github.com/irskep/persistproc-mcp/releases) for version history and changelogs.

## Uninstallation

To remove PersistProc:

```bash
pip uninstall persistproc
```

If you used a virtual environment, you can simply delete it:

```bash
rm -rf persistproc-env
```

---

**Next Steps**: After installation, head to the [Quick Start Guide](quick-start.md) to get PersistProc running!