# LitePaperReader — Usage Guide

## 1. Installation

```bash
git clone https://github.com/ASDNNB/litepaperreader
cd litepaperreader
pip install -e .           # core only
pip install -e .[pdf]      # + PDF support (docling)
pip install -e .[embed]    # + semantic embeddings (sentence-transformers)
pip install -e .[all]      # everything
```

Verify:

```bash
python -c "from litepaperreader import *; print(__version__)"
pytest tests/ -q
```

---

## 2. Model Integration

### Mock mode (no model, for testing)

Everything works with `mode="mock"` — keyword-based, deterministic, no dependencies.

```python
from litepaperreader.pipeline.extractor import SchemaExtractor
extractor = SchemaExtractor(registry, "paper", mode="mock")

from litepaperreader.knowledge.answer import AnswerGenerator
gen = AnswerGenerator(mode="mock")
```

### Ollama (local LLMs)

```bash
# 1. Install Ollama: https://ollama.com
# 2. Pull a model
ollama pull llama3.2
ollama pull qwen2.5:7b

# 3. Use in code
extractor = SchemaExtractor(registry, "paper",
    mode="ollama", model="llama3.2",
    api_base="http://localhost:11434")

gen = AnswerGenerator(mode="ollama", model="llama3.2",
    api_base="http://localhost:11434")
```

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
```

```python
extractor = SchemaExtractor(registry, "paper",
    mode="instructor", model="gpt-4o-mini",
    api_key="sk-...")

gen = AnswerGenerator(mode="openai", model="gpt-4o",
    api_key="sk-...")
```

---

## 3. MCP Server — LLM Plugin

The MCP server exposes 4 tools that any MCP-compatible LLM host can call.

### Start the server

```bash
python mcp_server.py
```

### Connect from Codex CLI

Add to your Codex CLI config:

```json
{
  "mcp_servers": [{
    "name": "litepaperreader",
    "command": "python",
    "args": ["path/to/mcp_server.py"]
  }]
}
```

### Connect from Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "litepaperreader": {
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  }
}
```

### Available tools

| Tool | What it does |
|------|-------------|
| `analyze_document` | Process a text, return structured cards with cell IDs |
| `get_cell_detail` | Drill down to a cell's source coordinates |
| `search_content` | Search processed documents |
| `answer_question` | Answer with cell-level citations |

---

## 4. Watch Mode — Automatic Processing

Monitor a directory and auto-process new/changed files:

```bash
# Process all supported files in ./docs recursively
python -m litepaperreader.pipeline.watcher --watch-dir ./docs --db index.db
```

This detects new/modified `.html`, `.txt`, `.md`, `.csv`, `.py` files,
runs the pipeline, and stores results in SQLite.

The MCP server can then load from the same database:

```bash
python mcp_server.py --db index.db
# Now LLM can search/answer across all processed files
```

### Supported file types

| Extension | Adapter | Content Type |
|-----------|---------|-------------|
| .html, .htm | HTMLAdapter | TEXT |
| .txt, .md | HTMLAdapter | TEXT |
| .csv, .tsv | TableAdapter | TABLE |
| .py, .js, .ts | CodeAdapter | CODE |
| .rs, .go, .java | CodeAdapter | CODE |
| .pdf | PDFAdapter | TEXT (with docling) |

---

## 5. Desktop Integration

### Background service (Windows)

Create `start_background.bat`:

```batch
@echo off
cd /d "C:\path\to\litepaperreader"
start /B pythonw mcp_server.py --db data\index.db --watch-dir data\inbox
```

Then add a shortcut to this batch file in `shell:startup` for auto-start.

### System tray (Windows + pystray)

```bash
pip install pystray pillow
```

Then use the system tray script (see `examples/tray_app.py`) to control
start/stop and view processing status from the system tray.

### Linux / macOS

Use systemd or launchd to run the MCP server as a daemon:

```bash
# systemd unit example
[Service]
ExecStart=/usr/bin/python /opt/litepaperreader/mcp_server.py --db /var/lib/litepaper/index.db --watch-dir /var/lib/litepaper/inbox
WorkingDirectory=/opt/litepaperreader
Restart=always
```

---

## 6. Using the DataPipeline API

```python
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.splitters import SemanticSplitter
from litepaperreader.pipeline.aggregators import RelationBuilder
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.knowledge.answer import AnswerGenerator
from litepaperreader.connectors.base import ResourceRef
import asyncio

# Define schema
reg = SchemaRegistry()
reg.register(SchemaTemplate("paper", "Academic paper", (
    FieldSpec("method", "Core method used"),
    FieldSpec("finding", "Key result"),
)))

# Build pipeline
pipeline = DataPipeline()
pipeline.add_default_adapters()
pipeline.toolchain.add_tool(SemanticSplitter())
pipeline.toolchain.add_tool(RelationBuilder())
pipeline.with_schema_extractor(reg, "paper", mode="ollama",
    model="llama3.2", api_base="http://localhost:11434")

# Process
async def run():
    ref = ResourceRef("fs", "/doc.html", content_type_hint="html")
    with open("/doc.html", "rb") as f:
        kp = await pipeline.run_raw(ref, f.read())
    gen = AnswerGenerator(mode="ollama", model="llama3.2",
        api_base="http://localhost:11434")
    answer = await gen.answer("What method does the paper propose?", kp)
    return answer

answer = asyncio.run(run())
print(answer.text)       # Answer with citations
print(answer.citations)  # [Citation(cell_id="...", text="...")]
```

---

## 7. Project Structure

```
litepaperreader/
  core/         Cell types, SchemaRegistry, HybridRetriever
  connectors/   FileSystem, Git, Web (source discovery)
  adapters/     HTML, Table, Code, PDF (format conversion)
  pipeline/     DAG toolchain, Orchestrator, Splitters, Extractor
  knowledge/    KnowledgePackage, AnswerGenerator
mcp_server.py   MCP protocol server for LLM integration
webui.py        Interactive web interface (http://localhost:8765)
tests/          75 tests
