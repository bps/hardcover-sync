set dotenv-load := true

# Default recipe - list available tasks
default:
    @just --list

# Install dependencies and set up development environment
install: && setenv
    uv sync
    uv run lefthook install
    just .calibre/source

# Write .env with Calibre configuration paths
setenv:
    -calibre-debug scripts/build_env.py

# Run unit tests (excludes Qt widget tests by default)
test *ARGS:
    LD_LIBRARY_PATH="${CALIBRE_LIBRARY_PATH:-}" uv run pytest {{ARGS}}

# Run Qt widget tests (requires display)
test-qt *ARGS:
    LD_LIBRARY_PATH="${CALIBRE_LIBRARY_PATH:-}" uv run pytest test/qt_tests/ -o "addopts=-v" {{ARGS}}

# Run tests with coverage report
coverage *ARGS:
    LD_LIBRARY_PATH="${CALIBRE_LIBRARY_PATH:-}" uv run pytest --cov --cov-report=term-missing --cov-report=html {{ARGS}}
    @echo "HTML report: htmlcov/index.html"

# Run linter and auto-fix issues
lint:
    uv run ruff check --fix src/ test/
    uv run ruff format src/ test/

# Check linting without fixing (for CI)
lint-check:
    uv run ruff check src/ test/
    uv run ruff format --check src/ test/

# Remove build artifacts and caches
clean:
    rm -rf dist build
    rm -rf .pytest_cache .ruff_cache .coverage
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Build the plugin zip file
build:
    bash scripts/bundle.sh

# Build and install plugin to Calibre
install-plugin: build
    @echo "Installing plugin..."
    CALIBRE_CONFIG_DIRECTORY="{{justfile_directory()}}/.calibre/config" calibre-customize --add-plugin dist/hardcover-sync-*.zip

# Launch Calibre in debug mode
calibre *ARGS:
    just .calibre/run -g {{ARGS}}

# Run plugin in CLI mode (for testing metadata sources)
run *ARGS:
    just .calibre/run -r "Hardcover Sync" -- {{ARGS}}

# Bump version using git-cliff
bump:
    bash scripts/bump.sh

# Generate changelog
changelog:
    git cliff --output CHANGELOG.md
