# Changelog

## 1.0.0-dev (2026-06-13)

### Features
- Core Cell type system with ContentType (TEXT / CODE / TABLE)
- VirtualPurifier — interval-based dirty-data skipping without source mutation
- SchemaRegistry — dynamic Pydantic model generation from templates
- HybridRetriever — BM25 + MiniLM with RRF fusion
- HTML, Table, Code, PDF format adapters
- FileSystem, Git, Web source connectors
- Toolchain DAG with topological ordering and parallel execution
- DataPipeline orchestrator with ``with_schema_extractor()``
- SchemaExtractor — 4 backends: mock, ollama, instructor, json
- AnswerGenerator — 4 backends with cell-level citations
- Cross-document RelationBuilder (keyword overlap + code dependency)
- MCP Server — 4 tools via Model Context Protocol
- PipelineDB + FileWatcher — SQLite persistence + directory monitoring
- YAML configuration system (``litepaper_config.yaml``)
- ProgressTracker with structured logging
- Chinese localization (Web UI, README_CN, error hints)
- Dockerfile + docker-compose.yml
- CI/CD workflow (GitHub Actions)

### Tests
- 91 tests, 4 skipped (optional dependencies)
- Cross-document pipeline integration test
- Schema YAML directory loading
- Error handling tests (LitePaperError hierarchy)
