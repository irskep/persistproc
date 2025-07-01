#!/bin/bash
set -e

# Create a virtual environment using uv if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  uv venv
fi

# Activate the virtual environment
source .venv/bin/activate

echo "Installing dependencies..."
uv pip install -e .

echo "Running persistproc..."
persistproc "$@" 