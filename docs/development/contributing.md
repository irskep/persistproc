# Contributing to PersistProc

Thank you for your interest in contributing to PersistProc! This guide will help you get started.

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/irskep/persistproc-mcp.git
   cd persistproc-mcp
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install in development mode**:
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
pytest tests/
```

## Code Style

We use:
- **Black** for code formatting
- **pytest** for testing
- **pre-commit** for git hooks

Install pre-commit hooks:
```bash
pre-commit install
```

## Submitting Changes

1. **Fork the repository** on GitHub
2. **Create a feature branch**: `git checkout -b feature-name`
3. **Make your changes** and add tests
4. **Run tests**: `pytest`
5. **Format code**: `black .`
6. **Commit your changes**: `git commit -m "Description"`
7. **Push to your fork**: `git push origin feature-name`
8. **Open a Pull Request**

## Documentation

To work on documentation:

```bash
# Install docs dependencies
pip install -r requirements-docs.txt

# Serve docs locally
mkdocs serve
```

## Reporting Issues

Please use GitHub Issues to report bugs or request features. Include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior

## Questions?

Feel free to open a discussion on GitHub or reach out to the maintainers.

---

**Happy contributing!** 🚀