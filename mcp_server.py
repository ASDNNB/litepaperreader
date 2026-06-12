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
            "Retrieve the full content and source coordinates of a specific "
            "extraction cell by its ID. Use this when you need to see the "
            "original source text behind a structured extraction. "
            "Returns source path, coordinates, and all extracted fields."
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
# JSON-RPC dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "initialize": lambda params: {
        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "litepaperreader", "version": "1.0.0"},
    },
    "tools/list": lambda _params: {"tools": TOOLS},
    "tools/call": lambda params: asyncio.run(
        _dispatch_tool(params["name"], params.get("arguments", {}))
    ),
}


async def _dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "analyze_document":
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
    _a, _ = parser.parse_known_args()
    if _a.config:
        from litepaperreader.pipeline.config import load_config
        _cfg = load_config(_a.config)
        if not _a.db and _cfg.db_path:
            _a.db = _cfg.db_path
        if not _a.watch_dir and _cfg.watch_dir:
            _a.watch_dir = _cfg.watch_dir
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
