 # Changelog

 All notable changes to LitePaperReader will be documented in this file.

 The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
 and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

 ## [Unreleased] — 1.0.0-dev

 ### Added

 - **Core Cell System** — Type-safe Cell types with ContentType (TEXT/CODE/TABLE/IMAGE),
   SourceRef with full provenance tracking, StructureMeta, and Relation support.
 - **VirtualPurifier** — Interval-fusion read-once algorithm for source text purification.
 - **Schema System** — Dynamic Pydantic models + YAML schema loading via SchemaRegistry,
   SchemaTemplate, and FieldSpec.
 - **HybridRetriever** — BM25 + reciprocal rank fusion (RRF), with optional semantic reranking.
 - **SemanticEncoder** — Dual-backend encoder supporting MiniLM and OpenAI embeddings.
 - **Source Connectors** — FileSystem (glob scanning), Git (ls-files tree walk), Web (HTTP + sitemap).
 - **Format Adapters** — HTMLAdapter (trafilatura + readability), TableAdapter (CSV/XLSX/Parquet),
   CodeAdapter (tree-sitter + fallback), PDFAdapter (docling).
 - **Pipeline Orchestrator** — DataPipeline with DAG toolchain, topological sort,
   serial/parallel execution, and `with_schema_extractor` integration.
 - **Toolchain** — SemanticSplitter, RelationBuilder, configurable filters and aggregators.
 - **SchemaExtractor** — Four extraction modes: mock, ollama, instructor (OpenAI), JSON.
 - **AnswerGenerator** — Four answer modes with cell-level citation tracking.
 - **KnowledgePackage** — StructuredCard + SummaryTree for cross-document knowledge representation.
 - **MCP Server** — Full MCP protocol server exposing 4 tools: `analyze_document`, `get_cell_detail`,
   `search_content`, `answer_question`.
 - **CI Pipeline** — GitHub Actions with Python 3.11 and 3.12 matrix testing.
 - **Tests** — 75+ test cases covering core, pipeline, extraction, retrieval, progress, and integration.
 - **Codex Plugin** — `.codex-plugin/plugin.json` for Codex CLI MCP integration.

 ### Infrastructure

 - `pyproject.toml` with optional dependency groups (dev, pdf, embed, code, web, yaml, all).
 - `Dockerfile` and `docker-compose.yml` for containerized deployment.
 - `litepaper_config.yaml` for pipeline, model, and watch mode configuration.
 - `docs/` with architecture goal, construction plan, and extraction guide.
 - Web UI via `webui.py` + `webui_template.html` for local dashboard.
 - `start_server.bat` for Windows background service.
 - `.gitignore`, `.dockerignore`, and `.github/workflows/ci.yml`.
