# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-02-11

### Bug Fixes

- Use svg in readme
- Handle bool column type in sync-from apply
- Allow 'Add books not in Calibre' checkbox when books are selected
- Deduplicate user_books and improve sync-from status messages
- Clean old builds before creating new zip in bundle script
- Move cancel button before link in link-book dialog

### Features

- Add is_read boolean column synced from reading status
- Add version string to UI
- Make sync-from-Hardcover selection-aware and targeted
- Multi-book linking with auto-link and deferred writes
- Switch hardcover identifier from numeric ID to slug

### Refactoring

- Add config helpers and type annotations
- Add API helpers and ListBookMembership model
- Deduplicate GraphQL query definitions
- Simplify sync logic with shared base and helpers
- Simplify matcher ISBN and slug lookups
- Clean up action.py imports and annotations
- Extract HardcoverDialogBase and simplify dialogs

### Testing

- Expand coverage for api, cache, matcher, and sync
- Add 51 tests for sync-to changes, truncation, and list memberships
## [0.2.0] - 2026-02-04

### Bug Fixes

- Exclude auto-generated _version.py from ruff checks

### CI/CD

- Add release workflow for GitHub releases

### Documentation

- Update changelog for v0.2.0

### Features

- Commit changelog in bump script

### Styling

- Update ruff version and format test_bundle.py
## [0.1.1] - 2026-02-04

### Bug Fixes

- Get version directly
- Remove _version.py
- Use vendored gql
## [0.1.0] - 2026-02-04

### Features

- Initial release of Hardcover Sync plugin

