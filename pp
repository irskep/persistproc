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

# Create a virtual environment using uv if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  uv venv
fi

# Activate the virtual environment
source .venv/bin/activate

echo "Installing dependencies..."
uv pip install -e ".[dev]"

# Change back to the original directory before running the user's command
cd "$ORIGINAL_CWD"

persistproc "$@"