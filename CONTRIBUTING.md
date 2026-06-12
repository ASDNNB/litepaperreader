# Contributing to LitePaperReader

## Development Setup

```bash
git clone https://github.com/ASDNNB/litepaperreader
cd litepaperreader
pip install -e .[dev]
```

## Code Style

- Type annotations required for all public functions
- Follow PEP 8 for Python code
- Use ``from __future__ import annotations`` at the top of every module

## Testing

```bash
pytest tests/ -v
```

Always run tests before submitting a PR. Add tests for new features.

## Pull Request Process

1. Branch from `master`
2. Write tests first (test-driven development)
3. Implement the feature or fix
4. Ensure all tests pass
5. Update CHANGELOG.md
6. Submit the PR

## Architecture Notes

Each new processing tool should subclass ``PipelineTool`` and implement ``process()``.
New data sources need a ``SourceConnector`` + ``FormatAdapter`` pair.
New extraction templates go in ``litepaperreader/schemas/`` as YAML files.
