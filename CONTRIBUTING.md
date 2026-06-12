 # Contributing to LitePaperReader

 We love contributions! Here's how to get started.

 ## Getting Started

 1. Fork the repository.
 2. Clone your fork:
    ```bash
    git clone https://github.com/your-username/litepaperreader.git
    cd litepaperreader
    ```
 3. Install development dependencies:
    ```bash
    pip install -e .[dev]
    ```
 4. Create a branch for your changes:
    ```bash
    git checkout -b feature/your-feature-name
    ```

 ## Development Guidelines

 ### Code Style

 - Follow PEP 8 conventions.
 - Use type hints for all function signatures.
 - Keep functions focused and single-purpose.
 - Write docstrings for public APIs.

 ### Testing

 - All new features must include tests.
 - Run the full test suite before submitting:
   ```bash
   pytest tests/ -v
   ```
 - For async tests, use `pytest-asyncio`.
 - Aim for at least 80% coverage on new code.

 ### Commit Messages

 Follow [Conventional Commits](https://www.conventionalcommits.org/):

 ```
 feat(core): add cross-document relation builder
 fix(pipeline): handle empty splitter output
 docs(readme): update MCP server examples
 test(retrieval): add BM25 edge case tests
 ```

 ## Pull Request Process

 1. Ensure all tests pass.
 2. Update documentation if you're changing behavior.
 3. Add a CHANGELOG entry under `[Unreleased]`.
 4. Submit the PR against the `master` branch.
 5. A maintainer will review and merge.

 ## Project Structure

 ```
 litepaperreader/
   core/         — Cell types, Schema, Retrieval, Embedding
   connectors/   — FileSystem, Git, Web source connectors
   adapters/     — HTML, Table, Code, PDF format adapters
   pipeline/     — DAG toolchain, Orchestrator, Splitters
   knowledge/    — KnowledgePackage, AnswerGenerator
 tests/          — Pytest test suite
 ```

 ## Questions?

 Open a [Discussion](https://github.com/ASDNNB/litepaperreader/discussions) or an Issue.

 Thank you for contributing!
