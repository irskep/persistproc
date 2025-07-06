#!/bin/bash
set -e

# Activate mise if it's installed to ensure we use the correct tool versions
if command -v mise &> /dev/null; then
  eval "$(mise activate bash)"
fi

# Store the original directory so we can switch back to it later
ORIGINAL_CWD=$(pwd)

# Get the directory of this script so it can be run from anywhere
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Change to the script's directory to ensure relative paths work correctly for setup
cd "$SCRIPT_DIR"

# Check if this is a help command to suppress mise output
if [[ " $* " =~ " --help " ]]; then
  # For help commands, run mise silently
  if command -v mise &> /dev/null; then
    mise deps:sync > /dev/null 2>&1
  else
    # Fallback: use uv directly, silently
    uv sync --extra docs --extra dev > /dev/null 2>&1
  fi
else
  # Use mise to sync dependencies if available, otherwise fall back to uv directly
  if command -v mise &> /dev/null; then
    mise deps:sync
  else
    # Fallback: use uv directly
    uv sync --extra docs --extra dev
  fi
fi

# Change back to the original directory before running the user's command
cd "$ORIGINAL_CWD"

# Use uv run to execute persistproc in the project environment  
uv run --module persistproc "$@"