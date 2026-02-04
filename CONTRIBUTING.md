# Contributing to Hardcover Sync

Thank you for your interest in contributing to Hardcover Sync! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- [mise](https://mise.jdx.dev/) for tool management
- [uv](https://docs.astral.sh/uv/) for Python package management (installed via mise)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/bps/hardcover-sync.git
cd hardcover-sync

# Install tools
mise install

# Install dependencies
uv sync

# Download Calibre source (for type hints)
just -f .calibre/justfile setup

# Install git hooks
uv run prek install
```

### Common Tasks

```bash
just test           # Run tests
just build          # Build plugin zip
just install-plugin # Install to test Calibre instance
just calibre        # Launch isolated test Calibre
just lint           # Run linter and formatter
```

## Code Style

This project uses:

- **[ruff](https://docs.astral.sh/ruff/)** for linting and formatting
- **Conventional Commits** for commit messages (enforced by gitlint)

The git hooks (via prek) will automatically check and format your code on commit.

### Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/). Format:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
- `feat(sync): add progress percentage sync`
- `fix(api): handle rate limiting errors`
- `docs: update installation instructions`

## Testing

### Running Tests

```bash
# Run all tests
just test

# Run with coverage report
just coverage

# Run specific test file
uv run pytest test/test_api.py -v

# Run integration tests (requires API token)
export HARDCOVER_API_TOKEN="your-token"
uv run pytest test/test_integration.py -v
```

### Writing Tests

- Place tests in the `test/` directory
- Use pytest fixtures and mocks
- Integration tests should use dry-run mode for mutations
- Aim for good coverage of new functionality

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with appropriate tests
3. Ensure all tests pass: `just test`
4. Ensure code is formatted: `just lint`
5. Commit with a conventional commit message
6. Open a pull request with a clear description

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Add tests for new functionality
- Reference any related issues

## Reporting Issues

When reporting issues, please include:

- Calibre version
- Plugin version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Any error messages or logs

## Questions?

Feel free to open an issue for questions or discussions about contributing.
