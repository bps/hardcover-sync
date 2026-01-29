# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Bug Fixes

- Improve sync dialog UX with better feedback
- Use correct Calibre API for custom column metadata
- Resolve first-click not working on plugin icon
- Remove hardcoded colors for dark mode compatibility
- Sync parent checkbox states with children on tree population
- Save hardcover identifier when creating new Calibre books
- Use relative import for matcher module in sync_from dialog
- Use review_raw field instead of review for Hardcover reviews
- Show errors in proper dialog instead of status label

### Build

- Add mise.toml for tool version management
- Add pyproject.toml with package configuration
- Add justfile with development tasks
- Add .calibre directory for Calibre dev environment
- Add build scripts for bundling and versioning
- Add git hooks and changelog configuration
- Add .gitignore for Python and Calibre development
- Add pytest shim for Calibre library path setup

### Documentation

- Add comprehensive implementation plan

### Features

- Add plugin skeleton with action, config, and icon
- Add Hardcover GraphQL API client with tests
- Add book linking with cache and matcher
- Implement reading status updates
- Complete phases 5-9 with Qt6 migration
- Add support for multiple reads via user_book_reads
- Add book grouping in sync preview and create README
- Display ratings as stars in sync dialogs
- Add option to create Calibre books from Hardcover library
- Populate all Hardcover fields when creating new Calibre books
- Add reading status filter for sync from Hardcover

### Miscellaneous

- Configure pyright to ignore missing Calibre runtime imports
- Remove redundant type ignore comments
- Exclude Qt-dependent files from coverage report
- Add custom plugin icon
- Prep for GitHub

### Refactoring

- Extract sync logic to testable module

### Reverts

- Remove pytest-qt setup in favor of mock-based testing

### Testing

- Add coverage task and increase test coverage
- Add pytest-qt for Qt widget tests

