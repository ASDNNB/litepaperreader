#!/usr/bin/env python3
"""LitePaperReader MCP Server -- expose document intelligence tools over Model Context Protocol.

Usage:
    # Run as stdio MCP server (for MCP hosts like Codex CLI, Claude Desktop)
    python mcp_server.py

    # Test directly (send JSON-RPC requests via stdin)
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}' | python mcp_server.py
"""
from __future__ import annotations
import pathlib

import asyncio
import hashlib
import json
import sys
import traceback
from typing import Any

from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.schema import FieldSpec, SchemaRegistry, SchemaTemplate
from litepaperreader.knowledge.answer import AnswerGenerator
from litepaperreader.pipeline.aggregators import RelationBuilder
from litepaperreader.pipeline.extractor import SchemaExtractor
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.splitters import SemanticSplitter
from litepaperreader.core.auto import (
    AutoConfig,
    PROMPT_DESIGN_SCHEMA,
    CODE_EXTENSIONS,
    auto_template_for,
    register_auto_templates,
    design_schema_from_description,
)

# ---------------------------------------------------------------------------
# Default schema templates
# ---------------------------------------------------------------------------

_registry = SchemaRegistry()
_registry.register(SchemaTemplate(
    template_id="paper",
    description="Academic paper",
    fields=(
        FieldSpec(name="title", description="Paper title"),
        FieldSpec(name="method", description="Core method used"),
        FieldSpec(name="finding", description="Key finding or result"),
    ),
))
_registry.register(SchemaTemplate(
    template_id="person", description="Person profile",
    fields=(
        FieldSpec(name="name", description="Full name of person"),
        FieldSpec(name="title", description="Job title or role"),
        FieldSpec(name="organization", description="Company or institution"),
    ),
))
_registry.register(SchemaTemplate(
    template_id="product", description="Product description",
    fields=(
        FieldSpec(name="name", description="Product name"),
        FieldSpec(name="feature", description="Key feature"),
        FieldSpec(name="price", description="Price or cost"),
    ),
))

# Register auto-detected templates used in --auto mode
register_auto_templates(_registry)

# Auto mode globals (set by --auto flag or YAML config)
_auto_config: AutoConfig | None = None
_active_schema: str | None = None  # template ID set by LLM via configure_schema


def _get_auto_registry() -> SchemaRegistry:
    """Return a registry with all auto templates + any custom schema."""
    r = SchemaRegistry()
    register_auto_templates(r)
    if _active_schema and _active_schema in _registry.list_templates():
        try:
            r.register(_registry._templates[_active_schema])
        except ValueError:
            pass
    return r


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------

_sessions: dict[str, dict[str, Any]] = {}


def _session_id(text: str) -> str:
    return "sess_" + hashlib.md5(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema for input)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_document",
        "description": (
            "Read a document file through LitePaperReader's smart processor. "
            "For small files, returns the raw content directly (fast, no overhead). "
            "For large files, auto-processes through the extraction pipeline "
            "and returns a structured knowledge package with summaries, "
            "extracted fields, and source citations for traceability. "
            "Use this instead of reading files directly for best results with large documents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "force_process": {
                    "type": "boolean",
                    "description": "Force LPR processing even for small files. Default: False",
                    "default": False,
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "configure_schema",
        "description": (
            "Tell LitePaperReader what information you want to extract from documents. "
            "Describe the document type and the fields you need. LPR will build "
            "a custom extraction schema and apply it to all subsequent read_document calls. "
            "Example: 'I need method name, dataset, accuracy, and limitations from ML papers'"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Describe the document type and fields to extract. E.g.: 'academic papers: title, method, dataset, accuracy, limitations'",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "analyze_document",
        "description": (
            "Process a text document and extract structured information. "
            "Returns a session_id (for follow-up calls), pipeline summary, "
            "and extracted cards with field values and cell IDs for traceability. "
            "Each card is a structured extraction (e.g. method, finding, title) "
            "and includes its source cell_id for later drill-down."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The full document text to analyze",
                },
                "template": {
                    "type": "string",
                    "description": "Schema template: paper, person, or product",
                    "default": "paper",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_cell_detail",
        "description": (
            "Retrieve the original source text + all extracted fields for a "
            "specific cell by its ID. When you need to drill down and read "
            "the actual original content behind a structured extraction, call "
            "this with the cell_id from any card. Returns: extracted fields, "
            "source coordinates, AND the original text from disk."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cell_id": {
                    "type": "string",
                    "description": "Cell ID from a previous analyze_document card (e.g. cell-0001:extracted)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID to scope the lookup",
                },
            },
            "required": ["cell_id"],
        },
    },
    {
        "name": "search_content",
        "description": (
            "Search through previously processed document content. "
            "Returns matching extraction cards with relevance scores. "
            "Use this when you need to find specific information across "
            "the processed document."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keyword or phrase)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID; uses most recent if omitted",
                },
                "max_results": {
                    "type": "number",
                    "description": "Maximum results to return (1-20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "answer_question",
        "description": (
            "Answer a question based on the processed document content. "
            "Returns an answer with cell-level citations so you can trace "
            "each claim back to its source. Use this for Q&A about the "
            "document after calling analyze_document."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to answer based on the document",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session ID; uses most recent if omitted",
                },
            },
            "required": ["question"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _analyze_document(args: dict[str, Any]) -> dict[str, Any]:
    text: str = args["text"]
    template: str = args.get("template", "paper")
    sid = _session_id(text)

    pipe = DataPipeline()
    pipe.add_default_adapters()
    pipe.toolchain.add_tool(SemanticSplitter(max_chars=1000, overlap_chars=100))
    pipe.toolchain.add_tool(RelationBuilder(strategy="keyword_overlap", min_overlap=2))

    if template not in _registry.list_templates():
        template = "paper"
    pipe.with_schema_extractor(_registry, template_id=template, mode="mock")

    html = f"<html><body><p>{text}</p></body></html>".encode()
    ref = ResourceRef(
        connector="mcp",
        resource_path=f"/input/{sid}.html",
        content_type_hint="html",
    )

    kp = await pipe.run_raw(ref, html)

    cards = [
        {
            "schema": c.schema_id,
            "cell_id": c.source_cell_id,
            "fields": {k: v for k, v in c.fields.items() if v is not None},
        }
        for c in kp.cards[:15]
    ]

    summary = (
        kp.summary_tree.summary
        if kp.summary_tree
        else f"{kp.metadata.get('num_cells', 0)} cells, {len(cards)} cards"
    )

    _sessions[sid] = {"kp": kp, "summary": summary, "template": template}

    result = {
        "session_id": sid,
        "summary": summary,
        "metadata": kp.metadata,
        "cards": cards,
    }
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}


def _get_cell_detail(args: dict[str, Any]) -> dict[str, Any]:
    cell_id: str = args["cell_id"]
    session_id: str | None = args.get("session_id")

    kp = None
    if session_id and session_id in _sessions:
        kp = _sessions[session_id]["kp"]
    else:
        for s in _sessions.values():
            for card in s["kp"].cards:
                if card.source_cell_id == cell_id:
                    kp = s["kp"]
                    break
            if kp:
                break

    if kp is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"error": "No session found. Call analyze_document first."}
                    ),
                }
            ],
        }

    for card in kp.cards:
        if card.source_cell_id == cell_id:
            ref = card.source_ref
            detail = {
                "cell_id": cell_id,
                "schema": card.schema_id,
                "fields": card.fields,
                "confidence": card.confidence,
                "source": {
                    "connector": ref.connector if ref else None,
                    "path": ref.resource_path if ref else None,
                    "span": (
                        {"start": ref.span.start, "end": ref.span.end}
                        if ref and ref.span
                        else None
                    ),
                },
            }
            return {
                "content": [
                    {"type": "text", "text": json.dumps(detail, ensure_ascii=False)}
                ],
            }

    return {
        "content": [
            {"type": "text", "text": json.dumps({"error": f"Cell {cell_id} not found"})}
        ],
    }


def _search_content(args: dict[str, Any]) -> dict[str, Any]:
    query: str = args.get("query", "")
    session_id: str | None = args.get("session_id")
    max_results: int = min(int(args.get("max_results", 5)), 20)

    kp = None
    if session_id and session_id in _sessions:
        kp = _sessions[session_id]["kp"]
    elif _sessions:
        kp = list(_sessions.values())[-1]["kp"]

    if kp is None:
        return {
            "content": [
                {"type": "text", "text": json.dumps({"error": "No session found"})}
            ],
        }

    ql = query.lower()
    results: list[dict[str, Any]] = []
    for card in kp.cards:
        score = 0
        for v in card.fields.values():
            if v and ql in str(v).lower():
                score += 1
        if score > 0:
            results.append(
                {
                    "cell_id": card.source_cell_id,
                    "schema": card.schema_id,
                    "fields": {k: v for k, v in card.fields.items() if v},
                    "score": score,
                }
            )

    results.sort(key=lambda x: -x["score"])
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"results": results[:max_results]}, ensure_ascii=False
                ),
            }
        ],
    }


async def _answer_question(args: dict[str, Any]) -> dict[str, Any]:
    question: str = args.get("question", "")
    session_id: str | None = args.get("session_id")

    kp = None
    if session_id and session_id in _sessions:
        kp = _sessions[session_id]["kp"]
    elif _sessions:
        kp = list(_sessions.values())[-1]["kp"]

    if kp is None:
        return {
            "content": [
                {"type": "text", "text": json.dumps({"error": "No session found"})}
            ],
        }

    gen = AnswerGenerator(mode="mock")
    answer = await gen.answer(question, kp)

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "answer": answer.text,
                        "citations": [
                            {"cell_id": c.cell_id, "text": c.text}
                            for c in answer.citations
                        ],
                        "confidence": answer.confidence,
                    },
                    ensure_ascii=False,
                ),
            }
        ],
    }



# ---------------------------------------------------------------------------
# read_document -- smart file reader with size-based auto-processing
# ---------------------------------------------------------------------------


async def _read_document(args: dict[str, Any]) -> dict[str, Any]:
    path_str: str = args["path"]
    force_process: bool = args.get("force_process", False)

    path = pathlib.Path(path_str)
    if not path.exists():
        return {
            "content": [{"type": "text", "text": json.dumps({"error": f"File not found: {path}"})}]
        }

    # Read file content
    raw_bytes = path.read_bytes()
    extension = path.suffix.lower()

    if extension in (".html", ".htm"):
        content_type_hint = "html"
    elif extension == ".pdf":
        content_type_hint = "pdf"
    elif extension in (".csv", ".xlsx", ".xls"):
        content_type_hint = "table"
    elif extension in CODE_EXTENSIONS:
        content_type_hint = "code"
    else:
        content_type_hint = "text"

    text_content = raw_bytes.decode("utf-8", errors="replace")
    text_len = len(text_content)
    ac = _auto_config or AutoConfig()

    if not force_process and text_len < ac.size_threshold:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "file": str(path),
                    "size_chars": text_len,
                    "processed": False,
                    "content": text_content,
                }, ensure_ascii=False),
            }]
        }

    template_id = auto_template_for(path_str)
    pipe = DataPipeline()
    pipe.add_default_adapters()
    pipe.toolchain.add_tool(SemanticSplitter(max_chars=1000, overlap_chars=100))
    pipe.toolchain.add_tool(RelationBuilder(strategy="keyword_overlap", min_overlap=2))

    effective_template = _active_schema or template_id
    auto_reg = _get_auto_registry()
    pipe.with_schema_extractor(
        auto_reg,
        template_id=effective_template,
        mode=ac.extraction_mode,
        model=ac.model_name,
        api_base=ac.api_base,
        api_key=ac.api_key,
    )

    ref = ResourceRef(
        connector="auto",
        resource_path=str(path),
        content_type_hint=content_type_hint,
    )

    try:
        kp = await pipe.run_raw(ref, raw_bytes)
    except Exception as exc:
        logger.warning("Pipeline processing failed, falling back to raw: %s", exc)
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "file": str(path),
                    "size_chars": text_len,
                    "processed": False,
                    "processed_error": str(exc),
                    "content": text_content[:100000],
                }, ensure_ascii=False),
            }]
        }

    # Auto code analysis -- layered structure + semantic (if complexity warrants LLM)
    code_analysis_result = None
    if content_type_hint == "code" and kp.cards:
        try:
            from litepaperreader.core.code_analyzer import (
                LayeredCodeAnalyzer, CodeAnalysisConfig, analyze_code_complexity,
            )
            code_cells = [c for c in kp.cards if hasattr(c, 'source_cell_id')]
            # Collect the actual Cell objects from the session (via kp metadata or stored cells)
            _code_cells_raw = getattr(kp, 'raw_cells', None) or kp.cards
            _level, _score, _note = analyze_code_complexity(kp.cards)
            code_analysis_result = {
                "escalated": _level.name != "STRUCTURE_ONLY",
                "level": _level.name,
                "complexity_score": _score,
                "note": _note,
            }
            if hasattr(kp, 'cards') and kp.cards:
                code_analysis_result["cards_analyzed"] = len(kp.cards)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Code analysis skipped: %s", exc)

    cards = [
        {
            "schema": c.schema_id,
            "cell_id": c.source_cell_id,
            "fields": {k: v for k, v in c.fields.items() if v is not None},
        }
        for c in kp.cards[:20]
    ]

    summary = (
        kp.summary_tree.summary
        if kp.summary_tree
        else f"{kp.metadata.get('num_cells', 0)} cells, {len(cards)} extractions"
    )

    sid = _session_id(str(path))
    _sessions[sid] = {"kp": kp, "summary": summary, "template": effective_template}

    result = {
        "file": str(path),
        "size_chars": text_len,
        "processed": True,
        "session_id": sid,
        "summary": summary,
        "extractions": cards,
        "metadata": kp.metadata,
        "total_cards": len(kp.cards),
    }

    if code_analysis_result:
        result["code_analysis"] = code_analysis_result

    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
    }


# ---------------------------------------------------------------------------
# configure_schema -- let the LLM define its own extraction schema
# ---------------------------------------------------------------------------


def _configure_schema(args: dict[str, Any]) -> dict[str, Any]:
    description: str = args.get("description", "")
    if not description:
        return {
            "content": [
                {"type": "text", "text": json.dumps({"error": "description is required"})}
            ]
        }

    template = design_schema_from_description(description, template_id="custom")

    global _active_schema
    try:
        _registry.register(template)
        _active_schema = "custom"
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "status": "ok",
                        "message": f"Schema configured with {len(template.fields)} fields",
                        "active_schema": "custom",
                        "fields": [f.name for f in template.fields],
                    }, ensure_ascii=False),
                }
            ]
        }
    except ValueError as exc:
        return {
            "content": [
                {"type": "text", "text": json.dumps({"error": str(exc)})}
            ]
        }


# ---------------------------------------------------------------------------
# MCP Resources -- expose filesystem via lpr:// URIs
# ---------------------------------------------------------------------------


def _list_resources(params: dict[str, Any]) -> dict[str, Any]:
    resources = []
    resources.append({
        "uri": "lpr://help",
        "name": "LitePaperReader Help",
        "description": "Information about using LPR transparent file processing",
        "mimeType": "text/plain",
    })
    return {"resources": resources}


def _read_resource(params: dict[str, Any]) -> dict[str, Any]:
    uri: str = params.get("uri", "")
    if uri == "lpr://help":
        text = (
            "LitePaperReader Auto Mode\n"
            "========================\n"
            "When you need to read a file, use the 'read_document' tool instead of\n"
            "reading files directly. LPR automatically:\n"
            "  - Detects small files (passthrough, zero overhead)\n"
            "  - Processes large files through its extraction pipeline\n"
            "  - Returns structured knowledge with source citations\n\n"
            "To configure extraction fields, call 'configure_schema' with a\n"
            "description of what you want to extract."
        )
        return {
            "contents": [
                {"uri": uri, "mimeType": "text/plain", "text": text}
            ]
        }
    return {
        "contents": [
            {"uri": uri, "mimeType": "text/plain", "text": f"Unknown resource: {uri}"}
        ]
    }


# ---------------------------------------------------------------------------
# MCP Prompts -- schema design prompt template
# ---------------------------------------------------------------------------


def _list_prompts(params: dict[str, Any]) -> dict[str, Any]:
    return {"prompts": [PROMPT_DESIGN_SCHEMA]}


def _get_prompt(params: dict[str, Any]) -> dict[str, Any]:
    name: str = params.get("name", "")
    arguments: dict[str, Any] = params.get("arguments", {})

    if name == "design_schema":
        description = arguments.get("description", "documents")
        return {
            "description": f"Design schema for: {description}",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": (
                            "I need you to describe what information you want to extract "
                            "from these documents so I can configure my extraction schema.\n\n"
                            f"Document type: {description}\n\n"
                            "Please list the specific fields (3-8) you want me to extract, "
                            "each with a short description of what it represents. "
                            "Then call 'configure_schema' with your description.\n\n"
                            "Example: 'Extract from academic papers: method name, "
                            "dataset used, accuracy metric, key limitations'"
                        ),
                    },
                }
            ],
        }

    return {
        "description": "Unknown prompt",
        "messages": [],
    }


# ---------------------------------------------------------------------------
# JSON-RPC dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "initialize": lambda params: {
        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": {},
        },
        "serverInfo": {
            "name": "litepaperreader",
            "version": "1.0.0",
            "description": "Smart document processor for LLMs -- auto-processes large files into structured knowledge",
        },
    },
    "tools/list": lambda _params: {"tools": TOOLS},
    "tools/call": lambda params: asyncio.run(
        _dispatch_tool(params["name"], params.get("arguments", {}))
    ),
    "resources/list": lambda params: _list_resources(params),
    "resources/read": lambda params: _read_resource(params),
    "prompts/list": lambda params: _list_prompts(params),
    "prompts/get": lambda params: _get_prompt(params),
}


async def _dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "read_document":
        return await _read_document(args)
    elif name == "configure_schema":
        return _configure_schema(args)
    elif name == "analyze_document":
        return await _analyze_document(args)
    elif name == "get_cell_detail":
        return _get_cell_detail(args)
    elif name == "search_content":
        return _search_content(args)
    elif name == "answer_question":
        return await _answer_question(args)
    else:
        raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    """Read JSON-RPC 2.0 requests from stdin, write responses to stdout."""
    import argparse
    parser = argparse.ArgumentParser()
    for flag in [("--config", None), ("--db", "SQLite DB"), ("--watch-dir", "Watch dir"), ("--template", "paper"), ("--mode", "mock"), ("--model", "gpt-4o-mini"), ("--api-base", None)]:
        kwargs = {"default": flag[1]} if flag[1] else {"default": None}
        if flag[0] in ("--template", "--mode", "--model"):
            kwargs["default"] = flag[1]
        parser.add_argument(flag[0], **kwargs)
    parser.add_argument("--auto", default=False, action="store_true",
        help="Enable transparent auto mode (smart file reading)")
    parser.add_argument("--auto", default=False, action="store_true",
        help="Enable transparent auto mode (smart file reading)")
    _a, _ = parser.parse_known_args()
    if _a.config:
        from litepaperreader.pipeline.config import load_config
        _cfg = load_config(_a.config)
        if not _a.db and _cfg.db_path:
            _a.db = _cfg.db_path
        if not _a.watch_dir and _cfg.watch_dir:
            _a.watch_dir = _cfg.watch_dir
    if _a.auto:
        from litepaperreader.core.auto import AutoConfig, register_auto_templates
        global _auto_config
        if _a.config:
            _cfg_dict = _cfg.__dict__ if hasattr(_cfg, "__dict__") else {}
        _auto_config = AutoConfig()
        # Override with environment variables for LLM (DeepSeek / OpenAI)
        import os as _os
        if _os.environ.get("LITEPAPER_API_KEY"):
            _auto_config.api_key = _os.environ["LITEPAPER_API_KEY"]
            _auto_config.api_base = _os.environ.get("LITEPAPER_API_BASE", "https://api.deepseek.com/v1")
            _auto_config.model_name = _os.environ.get("LITEPAPER_MODEL", "deepseek-chat")
            _auto_config.extraction_mode = _os.environ.get("LITEPAPER_MODE", "deepseek")
            sys.stderr.write("deepseek mode enabled via LITEPAPER_API_KEY\n")
            sys.stderr.flush()
        if not _a.db:
            _a.db = "litepaper_auto.db"
        sys.stderr.write("auto mode enabled (threshold=%d chars)\n" % _auto_config.size_threshold)
        sys.stderr.flush()
    if _a.db:
        from litepaperreader.pipeline.watcher import PipelineDB, FileWatcher, _default_registry
        _sessions["_db"] = PipelineDB(_a.db)
        if _a.watch_dir:
            FileWatcher(_a.watch_dir, _sessions["_db"], _default_registry,
                template_id=_a.template, mode=_a.mode, model=_a.model, api_base=_a.api_base).start()
            sys.stderr.write("watching " + _a.watch_dir + "\n")
            sys.stderr.flush()

    sys.stderr.write("litepaperreader mcp: ready\n")
    sys.stderr.flush()

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            msg: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            continue

        req_id = msg.get("id")
        method: str | None = msg.get("method")
        params: dict[str, Any] = msg.get("params", {})
        resp: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

        try:
            if method == "notifications/initialized":
                continue
            handler = _HANDLERS.get(method)
            if handler is None:
                resp["error"] = {"code": -32601, "message": f"Method not found: {method}"}
            else:
                resp["result"] = handler(params)
        except Exception as exc:
            sys.stderr.write(f"  error: {traceback.format_exc()}\n")
            sys.stderr.flush()
            resp["error"] = {"code": -32603, "message": str(exc)}

        if req_id is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
