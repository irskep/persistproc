#!/bin/bash
set -e

# Copy README.md to docs/index.md
cp README.md docs/index.md

# Copy CHANGELOG.md to docs/
cp CHANGELOG.md docs/

# Remove the 'full docs:' link line
sed -i.bak '/> Full docs:/d' docs/index.md

# Add coverage badge after the MIT license badge (only if coverage.svg exists)
if [ -f "docs/coverage.svg" ]; then
    sed -i.bak '/License: MIT/a\
![Test Coverage](coverage.svg)' docs/index.md
    echo "✅ Coverage badge added"
else
    echo "ℹ️  No coverage.svg found, skipping coverage badge"
fi

# Remove the backup file if it exists
[ -f docs/index.md.bak ] && rm docs/index.md.bak

# Update the help text in the docs
python scripts/update_docs_help.py

echo "✅ Help text updated in docs/tools.md" 