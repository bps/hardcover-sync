# Hardcover Sync

A Calibre plugin for bidirectional sync with [Hardcover.app](https://hardcover.app).

## Features

- **Sync reading status** between Calibre and Hardcover (Want to Read, Currently Reading, Read, Paused, Did Not Finish)
- **Sync metadata** including ratings, reading progress, dates started/finished, and reviews
- **Manage lists** - Add and remove books from your Hardcover lists
- **Link books** - Search Hardcover by ISBN or title to link Calibre books
- **Bidirectional sync** - Push changes to Hardcover or pull from Hardcover to Calibre

## Requirements

- Calibre 6.0 or later (Qt6)
- Python 3.10+
- A Hardcover.app account with an API token

## Installation

1. Download the latest release `.zip` file
2. In Calibre, go to **Preferences → Plugins → Load plugin from file**
3. Select the downloaded `.zip` file
4. Restart Calibre

## Setup

1. Get your API token from https://hardcover.app/account/api
2. In Calibre, go to **Preferences → Plugins → Hardcover Sync → Customize plugin**
3. Enter your API token and click **Validate**
4. Configure column mappings for the data you want to sync

### Recommended Custom Columns

Create these custom columns in Calibre (**Preferences → Add your own columns**):

| Column | Type | Suggested Name |
|--------|------|----------------|
| Status | Text | `#hc_status` |
| Rating | Rating or Float | `#hc_rating` |
| Progress | Integer | `#hc_progress` |
| Date Started | Date | `#hc_date_started` |
| Date Finished | Date | `#hc_date_read` |
| Review | Long text | `#hc_review` |

## Usage

### Menu Structure

```
Hardcover (toolbar button)
├── Set Status →
│   ├── Want to Read
│   ├── Currently Reading
│   ├── Read
│   ├── Paused
│   ├── Did Not Finish
│   └── Remove from Hardcover
├── Update Reading Progress...
├── Sync from Hardcover...
├── Sync to Hardcover...
├── Lists →
│   ├── Add to List...
│   ├── Remove from List...
│   └── View Lists on Hardcover
├── Link to Hardcover...
├── View on Hardcover
├── Remove Hardcover Link
├── Customize plugin...
└── Help
```

### Linking Books

Before syncing, books must be linked between Calibre and Hardcover:

1. Select one or more books in Calibre
2. Click **Hardcover → Link to Hardcover...**
3. Search by ISBN (automatic) or title
4. Select the matching Hardcover book

### Syncing

**Sync from Hardcover**: Pull your reading data from Hardcover into Calibre
- Fetches your entire Hardcover library
- Shows a preview of changes with checkboxes
- Only updates books that are already linked

**Sync to Hardcover**: Push your Calibre data to Hardcover
- Select books to sync
- Preview changes before applying
- Can add books to your Hardcover library or update existing entries

## Development

### Prerequisites

- [mise](https://mise.jdx.dev/) for tool management
- [just](https://just.systems/) for task running

### Setup

```bash
# Install tools
mise install

# Install dependencies
uv sync

# Download Calibre source (for type hints)
just -f .calibre/justfile setup
```

### Common Tasks

```bash
just test           # Run tests
just build          # Build plugin zip
just install-plugin # Install to test Calibre instance
just calibre        # Launch isolated test Calibre
just lint           # Run linter
just format         # Format code
```

### Running Tests

```bash
# Unit tests (mocked, no API token needed)
just test

# Integration tests (requires API token)
export HARDCOVER_API_TOKEN="your-token"
uv run pytest test/test_integration.py -v
```

Integration tests use read-only operations and dry-run mode for mutations, so they won't modify your Hardcover library.

## Acknowledgments

The development environment and build tooling for this plugin is based on [RobBrazier/calibre-plugins](https://github.com/RobBrazier/calibre-plugins). Thanks to Rob Brazier for the excellent foundation including:

- Calibre source download scripts for IDE support
- Plugin bundling and packaging scripts
- Test infrastructure with Calibre/Qt mocking
- Isolated Calibre instance for development

## License

GPL-3.0-or-later (same as Calibre)
