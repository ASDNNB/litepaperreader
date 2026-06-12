# Contributing to LitePaperReader

Thank you for your interest in contributing to LitePaperReader! This document provides guidelines and instructions for contributing.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## Development Setup

### Prerequisites

- Python 3.11+
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/ASDNNB/litepaperreader.git
cd litepaperreader

# Create virtual environment
python -m venv .venv

# Activate it
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Install in development mode
pip install -e .[dev]
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=litepaperreader --cov-report=term-missing
```

### Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check code style
ruff check litepaperreader/

# Auto-fix issues
ruff check litepaperreader/ --fix
```

## Pull Request Process

1. Create a feature branch from `master`
2. Make your changes
3. Add or update tests
4. Run the full test suite
5. Update `CHANGELOG.md` with your changes
6. Submit a PR with a clear description

### PR Checklist

- [ ] Tests pass (`pytest tests/ -v`)
- [ ] Code follows style (`ruff check litepaperreader/`)
- [ ] Public API changes are documented
- [ ] CHANGELOG.md is updated
- [ ] Commits are clean and atomic

## Project Structure

```
litepaperreader/
  core/          # Core data types, purifier, schema, retrieval, embedding
  connectors/    # Source discovery (filesystem, git, web)
  adapters/      # Format conversion (html, pdf, table, code)
  pipeline/      # DAG toolchain, splitters, extractors, filters
  knowledge/     # Knowledge package, answer generation
  schemas/       # Built-in YAML schema templates
tests/           # Test files (mirrors source structure)
docs/            # White paper, construction plan, guides
```

## Feature Requests

Open an issue with the `enhancement` label. Include:
- Use case description
- Proposed solution
- Alternative approaches considered

## Bug Reports

Open an issue with the `bug` label. Include:
- Minimal reproduction steps
- Expected vs actual behavior
- Environment details (OS, Python version, installation method)

## Questions?

Open a [Discussion](https://github.com/ASDNNB/litepaperreader/discussions) or check the [FAQ](README.md#-faq).
