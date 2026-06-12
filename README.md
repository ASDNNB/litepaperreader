# LitePaperReader

> **Universal Data Flow Intelligence Engine** — Type-safe, traceable, composable pipeline for documents, code, and data.

[![Version](https://img.shields.io/badge/version-1.0.0--dev-blue?style=flat-square)](https://github.com/ASDNNB/litepaperreader/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-brightgreen?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ASDNNB/litepaperreader/ci.yml?branch=master&style=flat-square)](https://github.com/ASDNNB/litepaperreader/actions)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![MCP](https://img.shields.io/badge/MCP-ready-purple?style=flat-square)](mcp_server.py)

English | [中文](README_CN.md)

## Why LitePaperReader?

Modern AI document processing has a fundamental gap: LLMs consume unstructured text, but real value lives in **structured, traceable information**. Existing tools either dump raw text into context windows or treat every document as an opaque blob.

**LitePaperReader** bridges this gap with a data flow pipeline that converts raw documents, code, and tables into typed, provenance-tracked cells, then extracts structured knowledge through a composable DAG of tools — all model-agnostic from end to end.

- **Type-Safe Cells** — Every piece of data carries a typed ContentType (TEXT / CODE / TABLE / IMAGE) so processing strategies are driven by types, not heuristics.
- **Absolute Provenance** — Every output is traceable back to source coordinates in the original file. No black-box extraction.
- **Composable DAG** — Not a fixed linear pipeline. Adapter → Splitter → Extractor → Filter → Aggregator — each edge chosen by you, for your data.
- **Model-Agnostic** — Each tool in the chain can independently choose its model scale. BM25 for batch coarsening, GPT-4 for high-precision extraction, MiniLM for embeddings. Mix freely.

## Key Features

### Data Pipeline
- **Multi-format input** — HTML, PDF, CSV, code files, plain text — each with a dedicated adapter and unified Cell output.
- **DAG toolchain** — Topologically-sorted, serial/parallel execution graph. Add, remove, or reorder tools without rewriting the pipeline.
- **Watch mode** — Monitor directories for new/changed files and auto-trigger processing with incremental indexing.

### Schema Extraction
- **Flexible schemas** — Define extraction schemas via Pydantic models or YAML files. Register once, reuse across documents.
- **Four extraction modes** — Mock (keyword-based, no model), Ollama (local LLMs), Instructor/OpenAI (cloud), JSON mode.
- **Field-level control** — Specify exactly what to extract per schema field, with source citations.

### MCP Integration
- **MCP server** — Expose the full pipeline as MCP tools. Any MCP-compatible LLM host (Codex CLI, Claude Desktop, etc.) can call nalyze_document, search_content, or nswer_question.
- **Cell-level citations** — Every answer comes with exact source coordinates, not fuzzy references.
- **Shared index** — Watch mode and MCP server share the same SQLite index for zero-lag incremental updates.

### Hybrid Retrieval
- **BM25 + dense (optional)** — Reciprocal rank fusion for best-of-both-worlds retrieval.
- **Semantic encoder** — Optional MiniLM or OpenAI embeddings for semantic search.
- **Cross-document awareness** — Relation Builder stitches cells across documents for cross-referencing.

## Screenshots

| Pipeline Architecture | Web UI | MCP Connection |
|----------------------|--------|----------------|
| _Diagram coming soon_ | _Screenshot coming soon_ | _Screenshot coming soon_ |

## Quick Start

### One-minute setup

`ash
pip install -e .
pytest tests/ -v
`

### Process a document

`python
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.knowledge.answer import AnswerGenerator
import asyncio

# 1. Define what to extract
reg = SchemaRegistry()
reg.register(SchemaTemplate("paper", "Academic paper", (
    FieldSpec("method", "Core method used"),
    FieldSpec("finding", "Key result"),
)))

# 2. Build the pipeline
pipeline = DataPipeline()
pipeline.add_default_adapters()
pipeline.with_schema_extractor(reg, "paper", mode="mock")

# 3. Run
async def run():
    ref = ResourceRef("fs", "paper.html", content_type_hint="html")
    with open("paper.html", "rb") as f:
        kp = await pipeline.run_raw(ref, f.read())
    gen = AnswerGenerator(mode="mock")
    answer = await gen.answer("What method does the paper propose?", kp)
    return answer

answer = asyncio.run(run())
print(answer.text)        # Answer with provenance
print(answer.citations)   # [Citation(cell_id="...", text="...")]
`

## Installation

### Core (no external model dependencies)

`ash
pip install -e .
`

### Optional dependency groups

| Group | Install | What it adds |
|-------|---------|-------------|
| PDF | pip install -e .[pdf] | PDF processing via docling & markitdown |
| Embeddings | pip install -e .[embed] | Semantic search (sentence-transformers + scikit-learn) |
| Code analysis | pip install -e .[code] | Multi-language AST parsing (tree-sitter) |
| Web fetching | pip install -e .[web] | HTTP & sitemap connectors (trafilatura + httpx) |
| YAML schemas | pip install -e .[yaml] | YAML schema loading |
| **All** | pip install -e .[all] | Everything above |

> **Requires Python 3.11+**

### Development

`ash
pip install -e .[dev]
pytest tests/ -v
`

## MCP Server — LLM Plugin

LitePaperReader ships as an MCP server, making it a first-class plugin for any MCP-compatible LLM host.

`ash
python mcp_server.py
`

### Connect from Codex CLI

Add to your Codex CLI config:

`json
{
  "mcp_servers": [
    {
      "name": "litepaperreader",
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  ]
}
`

### Connect from Claude Desktop

Add to claude_desktop_config.json:

`json
{
  "mcpServers": {
    "litepaperreader": {
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  }
}
`

### Available Tools

| Tool | Description |
|------|-------------|
| nalyze_document | Process a document and return structured cards with cell IDs |
| get_cell_detail | Drill down to a cell's source coordinates in the original file |
| search_content | Search across all processed documents |
| nswer_question | Answer a question with cell-level citations |

## Architecture

`
Raw Data → Source Connectors → Format Adapters → Cell Data Stream → Toolchain DAG → Knowledge Package → Answer
          (File/Git/Web)        (HTML/CSV/PDF/Code)   (Typed Cells)     (Split/Extract/Relate) (Structured Cards) (With Citations)
`

`
litepaperreader/
  core/           Cell types, SchemaRegistry, HybridRetriever, SemanticEncoder
  connectors/     FileSystem, Git, Web — sources of raw data
  adapters/       HTML, Table, Code, PDF — format-to-Cell conversion
  pipeline/       DAG toolchain, Orchestrator, Splitters, Extractor, Aggregators
  knowledge/      KnowledgePackage, AnswerGenerator
mcp_server.py     MCP protocol server for LLM integration
webui.py          Local web dashboard (http://localhost:8765)
tests/            75+ tests across all modules
`

## Model Integration

LitePaperReader works **without any LLM** via mock mode. When you need real AI extraction:

### Ollama (local)

`ash
ollama pull llama3.2
`

`python
extractor = SchemaExtractor(reg, "paper",
    mode="ollama", model="llama3.2",
    api_base="http://localhost:11434")
`

### OpenAI

`ash
export OPENAI_API_KEY="sk-..."
`

`python
extractor = SchemaExtractor(reg, "paper",
    mode="instructor", model="gpt-4o-mini")
`

## Watch Mode

Monitor a directory and auto-process new/changed files:

`ash
python -m litepaperreader.pipeline.watcher --watch-dir ./docs --db index.db
`

The MCP server can then load from the same database:

`ash
python mcp_server.py --db index.db
`

### Supported file types

| Extension | Adapter |
|-----------|---------|
| .html, .htm, .txt, .md | HTMLAdapter |
| .csv, .tsv | TableAdapter |
| .py, .js, .ts, .rs, .go, .java | CodeAdapter |
| .pdf | PDFAdapter (with docling) |

## FAQ

**Q: Does this need a GPU or an LLM API key?**
A: No. Mock mode works entirely with keyword-based extraction and deterministic answers. LLMs are optional for higher quality.

**Q: How is this different from LangChain / LlamaIndex?**
A: Those frameworks solve "how to call LLMs." LitePaperReader solves "how to turn raw data into structured, traceable information that LLMs can consume." The pipeline is type-safe, provenance-tracked, and model-agnostic — not a chain of LLM calls.

**Q: Can I use this with my own LLM?**
A: Yes. LitePaperReader is model-agnostic. Every extraction/answer tool accepts a mode parameter — mock, ollama, openai, or custom.

**Q: What about large documents?**
A: The SemanticSplitter chunks intelligently. The VirtualPurifier ensures source text is read-once, with fused intervals. No redundant processing.

**Q: Can I watch multiple directories?**
A: Yes. Start separate watcher processes with their own --db paths, or use the MCP server's shared index.

## Contributing

Issues and PRs are welcome!

1. Fork the repo and create a branch: git checkout -b feature/my-feature
2. Install development dependencies: pip install -e .[dev]
3. Write tests for your change
4. Run all tests: pytest tests/ -v
5. Submit a PR

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

## License

[MIT](LICENSE) © 2026 LitePaperReader

[View on GitHub](https://github.com/ASDNNB/litepaperreader)
