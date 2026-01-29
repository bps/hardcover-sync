#!/usr/bin/env bash
#
# Bump the plugin version using git-cliff to analyze commits
# and determine the next semantic version.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Get current version from latest tag or default to 0.0.0
CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "0.0.0")
CURRENT_VERSION="${CURRENT_TAG#v}" # Remove 'v' prefix if present

echo "Current version: $CURRENT_VERSION"

# Use git-cliff to determine next version based on commits
# --bumped-version outputs just the new version number
NEXT_VERSION=$(git cliff --bumped-version 2>/dev/null | tr -d '\n' || echo "")

if [[ -z "$NEXT_VERSION" ]]; then
	echo "No version bump needed based on commits, or git-cliff not configured."
	echo "Manually specify: ./scripts/bump.sh <version>"
	exit 1
fi

# Remove 'v' prefix if git-cliff added one
NEXT_VERSION="${NEXT_VERSION#v}"

echo "Next version: $NEXT_VERSION"

# Confirm with user
read -p "Create tag v$NEXT_VERSION? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
	echo "Aborted."
	exit 1
fi

# Create annotated tag
git tag -a "v$NEXT_VERSION" -m "Release v$NEXT_VERSION"

echo "Created tag v$NEXT_VERSION"
echo "Push with: git push origin v$NEXT_VERSION"
