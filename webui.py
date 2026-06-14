"""LitePaperReader Web UI -- built-in HTTP server, no extra dependencies.

Usage:
    python webui.py
    # Open http://localhost:8765
"""
from __future__ import annotations

import asyncio
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.splitters import SemanticSplitter
import os
from litepaperreader.knowledge.answer import AnswerGenerator

# ---------------------------------------------------------------------------
# Default schema templates
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, SchemaTemplate] = {
    "paper": SchemaTemplate(
        template_id="paper",
        description="Academic Paper",
        fields=(
            FieldSpec(name="title", description="Paper title"),
            FieldSpec(name="method", description="Core method used"),
            FieldSpec(name="finding", description="Key finding or result"),
        ),
    ),
    "person": SchemaTemplate(
        template_id="person",
        description="Person Profile",
        fields=(
            FieldSpec(name="name", description="Full name of person"),
            FieldSpec(name="title", description="Job title or role"),
            FieldSpec(name="organization", description="Company or institution"),
        ),
    ),
    "product": SchemaTemplate(
        template_id="product",
        description="Product Description",
        fields=(
            FieldSpec(name="name", description="Product name"),
            FieldSpec(name="feature", description="Key feature"),
            FieldSpec(name="price", description="Price or cost"),
        ),
    ),
}

_registry = SchemaRegistry()
for _t in DEFAULT_TEMPLATES.values():
    _registry.register(_t)


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

async def run_pipeline(input_text: str, template_id: str, mode: str) -> dict[str, Any]:
    """Run the full pipeline: input -> adapters -> splitter -> extractor -> answer."""
    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.toolchain.add_tool(SemanticSplitter(max_chars=1000, overlap_chars=100))
    pipeline.with_schema_extractor(_registry, template_id=template_id, mode=mode)

    html = f"<html><body><p>{input_text}</p></body></html>".encode()
    ref = ResourceRef(
        connector="webui",
        resource_path="/input.html",
        content_type_hint="html",
    )

    kp = await pipeline.run_raw(ref, html)

    gen = AnswerGenerator(mode=mode)
    answer = await gen.answer("What information can you extract?", kp)

    return {
        "metadata": kp.metadata,
        "cards": [
            {
                "schema_id": c.schema_id,
                "fields": c.fields,
                "source_cell_id": c.source_cell_id,
            }
            for c in kp.cards
        ],
        "answer": {
            "text": answer.text,
            "citations": [
                {"cell_id": cit.cell_id, "text": cit.text} for cit in answer.citations
            ],
        },
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    """HTTP request handler for the Web UI."""

    def do_GET(self):
        if self.path == "/":
            self._serve_html()
        elif self.path == "/templates":
            self._handle_list_templates()
        elif self.path.endswith(".js"):
            self._serve_static("text/javascript")
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/process":
            self._handle_process()
        elif self.path == "/schema":
            self._handle_create_schema()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))

    def _serve_static(self, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def _handle_process(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                run_pipeline(
                    data.get("text", ""),
                    data.get("template", "paper"),
                    data.get("mode", "mock"),
                )
            )
            loop.close()
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)}, status=500)

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _handle_create_schema(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))
        try:
            fields = tuple(
                FieldSpec(name=f["name"], description=f.get("description", ""))
                for f in body.get("fields", [])
            )
            template = SchemaTemplate(
                template_id=body["template_id"],
                description=body.get("description", ""),
                fields=fields,
            )
            _registry.register(template)
            self._json_response({"success": True, "template_id": body["template_id"]})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass  # Quiet by default

    def _handle_list_templates(self):
        self._json_response({"templates": list(_registry.list_templates())})

def log_message(self, fmt: str, *args: Any) -> None:
        pass  # Quiet by default


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

# Note: This is intentionally kept as a single string constant so the entire
# web UI is self-contained in one file. The HTML is a simple but functional
# interface for testing the data pipeline interactively.

import pathlib
_HERE = pathlib.Path(__file__).parent
_TEMPLATE = _HERE / "webui_template.html"
HTML_PAGE = _TEMPLATE.read_text(encoding="utf-8") if _TEMPLATE.exists() else "<html><body>Template not found</body></html>"



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(port: int = 8765):
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"  LitePaperReader Web UI")
    print(f"  http://localhost:{port}")
    print(f"  Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
