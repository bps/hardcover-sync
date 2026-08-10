#!/usr/bin/env bash
# Print the release or development version for a plugin bundle.

set -euo pipefail

PROJECT_DIR="${1:-.}"
VERSION_TAG_PATTERN='v[0-9]*'

if EXACT_TAG=$(git -C "$PROJECT_DIR" describe --tags --exact-match \
	--match "$VERSION_TAG_PATTERN" 2>/dev/null) \
	&& [[ -z "$(git -C "$PROJECT_DIR" status --porcelain)" ]]; then
	printf '%s\n' "${EXACT_TAG#v}"
	exit 0
fi

BASE_TAG=$(git -C "$PROJECT_DIR" describe --tags --abbrev=0 \
	--match "$VERSION_TAG_PATTERN" 2>/dev/null || printf 'v0.0.0')
COMMIT_ID=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || printf 'unknown')
printf '%s-g%s\n' "${BASE_TAG#v}" "$COMMIT_ID"
