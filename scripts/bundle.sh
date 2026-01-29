#!/usr/bin/env bash
#
# Bundle the Hardcover Sync plugin into a distributable zip file.
# This script:
#   1. Installs the package and dependencies to a temp directory
#   2. Moves plugin code to the root (Calibre expects this structure)
#   3. Creates a versioned zip file in dist/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_NAME="hardcover-sync"
PACKAGE_NAME="hardcover_sync"

cd "$PROJECT_DIR"

# Get version from versioningit or fallback
VERSION=$(uv run python -c "
try:
    from versioningit import get_version
    print(get_version('.'))
except Exception:
    print('0.0.0.dev0')
")

echo "Building $PLUGIN_NAME version $VERSION..."

# Create temp build directory
BUILD_DIR=$(mktemp -d)
trap "rm -rf $BUILD_DIR" EXIT

# Install package with dependencies (excluding dev deps)
echo "Installing package to build directory..."
uv pip install . --target "$BUILD_DIR" --quiet --reinstall-package hardcover-sync

# Move plugin package contents to root of build directory
# Calibre expects plugin files at the root of the zip
echo "Restructuring for Calibre..."
if [[ -d "$BUILD_DIR/$PACKAGE_NAME" ]]; then
	# Move package contents to root
	mv "$BUILD_DIR/$PACKAGE_NAME"/* "$BUILD_DIR/"
	rmdir "$BUILD_DIR/$PACKAGE_NAME"
fi

# Create plugin-import-name file for Calibre's plugin loader
# This tells Calibre what module name to use for the plugin
touch "$BUILD_DIR/plugin-import-name-$PACKAGE_NAME.txt"

# Copy images directory if not already present
if [[ -d "src/$PACKAGE_NAME/images" ]] && [[ ! -d "$BUILD_DIR/images" ]]; then
	cp -r "src/$PACKAGE_NAME/images" "$BUILD_DIR/"
fi

# Clean up unwanted files
echo "Cleaning up..."
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
rm -rf "$BUILD_DIR/bin" 2>/dev/null || true
rm -f "$BUILD_DIR/.lock" 2>/dev/null || true

# Create dist directory
mkdir -p "$PROJECT_DIR/dist"

# Create the zip file
ZIP_NAME="${PLUGIN_NAME}-${VERSION}.zip"
ZIP_PATH="$PROJECT_DIR/dist/$ZIP_NAME"

echo "Creating $ZIP_NAME..."
(cd "$BUILD_DIR" && zip -rq "$ZIP_PATH" .)

echo "Built: dist/$ZIP_NAME"
echo "Size: $(du -h "$ZIP_PATH" | cut -f1)"
