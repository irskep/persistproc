"""
PersistProc: Manage and monitor long-running processes via MCP.

This package provides process management capabilities through an MCP server interface,
allowing users to start, stop, monitor, and retrieve logs from long-running processes.
"""

from .core import ProcessManager, LogManager, ProcessInfo, process_info_to_dict
from .utils import get_iso_timestamp, escape_command, get_app_data_dir, setup_logging
from .server import create_app, setup_signal_handlers

# Package metadata
__version__ = "0.1.0"
__author__ = "PersistProc Contributors"

# Public API
__all__ = [
    "ProcessManager",
    "LogManager",
    "ProcessInfo",
    "process_info_to_dict",
    "get_iso_timestamp",
    "escape_command",
    "get_app_data_dir",
    "setup_logging",
    "create_app",
    "setup_signal_handlers",
]

# Global instance - will be initialized in server module
process_manager = None
