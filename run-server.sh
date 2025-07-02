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

echo "Formatting with black..."
black .

# Change back to the original directory before running the user's command
cd "$ORIGINAL_CWD"

echo "Running persistproc..."

# Separate the --raw flag from the command arguments
persistproc_flags=()
command_args=()
for arg in "$@"; do
    if [[ "$arg" == "--raw" ]]; then
        persistproc_flags+=("--raw")
    else
        command_args+=("$arg")
    fi
done

persistproc "${persistproc_flags[@]}" "${command_args[@]}" 