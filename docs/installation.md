# Installation

This guide covers the installation of `persistproc`.

## System Requirements

*   **Operating System**: A Unix-like environment (Linux, macOS) is recommended.
*   **Python**: Version 3.10 or higher.

## Installation Steps

`persistproc` is a Python package installed from PyPI. A virtual environment is a best practice to avoid conflicts with system-wide packages.

1.  **Create and activate a virtual environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install the package**:
    ```bash
    pip install persistproc
    ```

3.  **Verify the installation**:
    Check that the command is available by viewing its help output.
    ```bash
    persistproc --help
    ```
    This confirms that the script is in your path and executable.

4.  **Start the Server**:
    The server is the core component that manages all processes. Run it in a dedicated terminal that you intend to keep open.
    ```bash
    persistproc --serve
    ```
    By default, the server listens on `127.0.0.1:8947`. 