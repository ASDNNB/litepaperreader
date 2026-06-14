# Changelog

All notable changes to LitePaperReader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- One-click bootstrap installer: `get-litepaperreader.py` — works on Windows/macOS/Linux
- Windows .exe installer: build via `build_exe.py` or GitHub Actions
- Professional README with badges, architecture diagram, and gallery
- Chinese documentation (README_CN.md)
- GitHub Issue/PR templates (bug report, feature request, PR checklist)
- CI/CD workflows: cross-platform testing, linting, .exe build, PyPI release
- `.editorconfig`, `Makefile`, `FUNDING.yml` for project standardization
- Multi-platform GitHub Actions matrix (Windows/macOS/Linux + Python 3.11/3.12)

### Changed
- Complete README rewrite with bilingual support
- Updated pyproject.toml with proper classifiers and metadata
- Enhanced error handling across the codebase

## [1.0.0-dev] - 2026-06-12

### Added
- Core data types: Cell, SourceRef, ContentType, StructureMeta, Relation
- VirtualPurifier: interval-based dirty data removal
- SchemaRegistry: dynamic Pydantic model generation from YAML/Python
- HybridRetriever: BM25 + MiniLM + RRF fusion
- SemanticEncoder: MiniLM and OpenAI backends
- Source connectors: FileSystem, Git, Web
- Format adapters: HTML, PDF, Table (CSV/XLSX), Code (tree-sitter)
- Pipeline toolchain: DAG-based composable processing
- SchemaExtractor: 4 backends (mock, ollama, instructor, json)
- AnswerGenerator: 4 backends with Cell-level citations
- KnowledgePackage: structured cards + summary tree + provenance map
- MCP Server: 4 tools via Model Context Protocol
- Web UI: zero-dependency browser interface
- File watcher: directory monitoring with auto-processing
- YAML configuration system
- Docker support
- 91 passing tests
