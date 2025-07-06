import os
import sys
from rich.console import Console

# Configure console for Windows compatibility
# Handle Unicode encoding errors that occur on Windows with cp1252 encoding

# Set UTF-8 environment for Windows to prevent encoding issues
if os.name == "nt":
    # Force UTF-8 encoding on Windows
    os.environ.setdefault("PYTHONUTF8", "1")

    # Reconfigure stdout/stderr with UTF-8 encoding and error handling
    try:
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
    except (AttributeError, OSError):
        # Fallback if buffer attribute doesn't exist or reconfiguration fails
        pass

console = Console()
