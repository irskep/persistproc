#!/bin/bash
set -e

# Copy README.md to docs/index.md
cp README.md docs/index.md

# Remove the 'full docs:' link line
sed -i.bak '/> Full docs:/d' docs/index.md

# Add coverage badge after the MIT license badge
sed -i.bak '/License: MIT/a\
![Test Coverage](coverage.svg)' docs/index.md

# Remove the backup file
rm docs/index.md.bak

echo "✅ Coverage badge generated"

# Update the help text in the docs
python scripts/update_docs_help.py

echo "✅ Help text updated in docs/tools.md" 