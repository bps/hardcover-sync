<p align="center">
  <img src="src/hardcover_sync/images/hardcover_sync.png" alt="Hardcover Sync" width="128" height="128">
</p>

# Hardcover Sync

A Calibre plugin for bidirectional sync with [Hardcover.app](https://hardcover.app).

## Features

- **Sync reading status** between Calibre and Hardcover (Want to Read, Currently Reading, Read, Paused, Did Not Finish)
- **Sync metadata** including ratings, reading progress, dates started/finished, and reviews
- **Bidirectional sync** - Push changes to Hardcover or pull from Hardcover to Calibre

## Requirements

- Calibre 6.0 or later (Qt6)
- A Hardcover.app account with an API token

## Installation

1. Download the latest release `.zip` file
2. In Calibre, go to **Preferences → Plugins → Load plugin from file**
3. Select the downloaded `.zip` file
4. Restart Calibre

## Setup

   > [!WARNING]
   > Your API token is stored in cleartext in Calibre's plugin configuration. Keep your Calibre configuration directory secure and do not share your `plugins/Hardcover Sync.json` file.

1. Get your API token from https://hardcover.app/account/api
2. In Calibre, go to **Preferences → Plugins → Hardcover Sync → Customize plugin**
3. Enter your API token and click **Validate**
4. Configure column mappings for the data you want to sync

### Recommended custom columns

Create these custom columns in Calibre (**Preferences → Add your own columns**):

| Column | Type | Suggested Name |
|--------|------|----------------|
| Status | Text | `#hc_status` |
| Rating | Rating | `#hc_rating` |
| Progress (pages) | Integer | `#hc_progress` |
| Progress (%) | Float | `#hc_progress_pct` |
| Date Started | Date | `#hc_date_started` |
| Date Finished | Date | `#hc_date_read` |
| Review | Long text | `#hc_review` |

You can use pre-defined Calibre columns as well (e.g. rating).

You can use either or both progress columns:
- **Progress (pages)** - Integer column for page number (e.g., 150)
- **Progress (%)** - Float column for percentage (e.g., 50.0)

Hardcover stores both values and converts between them based on the book's page count.

#### Date column format

I use `yyyy-MM-dd`. Check the [docs for the format string](https://manual.calibre-ebook.com/generated/en/template_ref.html#id45).

## Usage

### Menu structure

```
Hardcover (toolbar button)
├── Set Status →
│   ├── Want to Read
│   ├── Currently Reading
│   ├── Read
│   ├── Paused
│   ├── Did Not Finish
│   └── Remove from Hardcover
├── Sync from Hardcover...
├── Sync to Hardcover...
├── Link to Hardcover...
├── View on Hardcover
├── Remove Hardcover Link
├── Customize plugin...
└── Help
```

### Linking books

Before syncing, books must be linked between Calibre and Hardcover:

1. Select one or more books in Calibre
2. Click **Hardcover → Link to Hardcover...**
3. Search by ISBN (automatic) or title
4. Select the matching Hardcover book

### Syncing

**Sync from Hardcover**: Pull your reading data from Hardcover into Calibre
- Fetches your Hardcover library
- Shows a preview of changes with checkboxes
- Only updates books that are already linked

**Sync to Hardcover**: Push your Calibre data to Hardcover
- Select books to sync
- Preview changes before applying
- Can add books to your Hardcover library or update existing books

## Development

### Prerequisites

- [mise](https://mise.jdx.dev/) for tool management

### Setup

```bash
# Install tools
mise install

# Install dependencies
uv sync

# Download Calibre source (for type hints)
just -f .calibre/justfile setup
```

### Common tasks

```bash
just test           # Run tests
just build          # Build plugin zip
just install-plugin # Install to test Calibre instance
just calibre        # Launch isolated test Calibre
just lint           # Run linter
just format         # Format code
```

### Running tests

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

He wrote the Hardcover metadata source plugin linked above. It's excellent.

## License

GPL-3.0-or-later (same as Calibre)
