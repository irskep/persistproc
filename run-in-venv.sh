#!/bin/bash
set -e

# Execute the command in the uv-managed virtual environment
exec uv run -- "$@"
