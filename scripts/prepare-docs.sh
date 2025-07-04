#!/bin/bash
set -e

# Copy README.md to docs/index.md
cp README.md docs/index.md

# Copy coverage.svg to docs/
cp coverage.svg docs/coverage.svg

# Remove the 'full docs:' link line
sed -i.bak '/> Full docs:/d' docs/index.md

# Remove the backup file
rm docs/index.md.bak

echo "✅ README.md copied to docs/index.md with 'full docs:' link removed" 