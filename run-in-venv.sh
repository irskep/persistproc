#!/bin/bash
# Convenience script to run a command with the virtualenv activated
# Usage: ./run-in-venv.sh python script.py [args...]
#        ./run-in-venv.sh pytest tests/
#        ./run-in-venv.sh python -c "import persistproc; print('OK')"

set -e

# Get the directory of this script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Activate the virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Run the command with all arguments passed through
exec "$@"