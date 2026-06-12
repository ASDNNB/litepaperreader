"""File watcher and SQLite persistence for pipeline output.

Usage:
    python -m litepaperreader.pipeline.watcher --watch-dir ./docs --db index.db

This monitors a directory for new/changed files, runs them through the
pipeline, and stores results in SQLite for the MCP server to query.
"""
from __future__ import annotations
import pathlib

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.splitters import SemanticSplitter
from litepaperreader.pipeline.aggregators import RelationBuilder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default schema (register built-in templates)
# ---------------------------------------------------------------------------

_default_registry = SchemaRegistry()
_default_registry.register(SchemaTemplate(
    template_id="paper", description="Academic paper",
    fields=(
        FieldSpec(name="title", description="Paper title"),
        FieldSpec(name="method", description="Core method used"),
        FieldSpec(name="finding", description="Key finding or result"),
    ),
))
_default_registry.register(SchemaTemplate(
    template_id="person", description="Person profile",
    fields=(
        FieldSpec(name="name", description="Full name of person"),
        FieldSpec(name="title", description="Job title or role"),
        FieldSpec(name="organization", description="Company or institution"),
    ),
))
_default_registry.register(SchemaTemplate(
    template_id="product", description="Product description",
    fields=(
        FieldSpec(name="name", description="Product name"),
        FieldSpec(name="feature", description="Key feature"),
        FieldSpec(name="price", description="Price or cost"),
    ),
))

# Supported file extensions mapped to content type hints
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".html": "html", ".htm": "html",
    ".txt": "text", ".md": "markdown",
    ".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx",
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".rs": "rust", ".go": "go", ".java": "java",
    ".pdf": "pdf",
}

# ---------------------------------------------------------------------------
# PipelineDB — SQLite persistence
# ---------------------------------------------------------------------------


class PipelineDB:
    """Persistent SQLite storage for pipeline results."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._lock = threading.Lock()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                size INTEGER DEFAULT 0,
                processed_at TEXT NOT NULL,
                session_id TEXT
            );
            CREATE TABLE IF NOT EXISTS cells (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                body TEXT,
                source_span TEXT,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                cell_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                schema_id TEXT NOT NULL,
                fields TEXT NOT NULL,
                confidence REAL DEFAULT 1.0
            );
            CREATE INDEX IF NOT EXISTS idx_cards_session ON cards(session_id);
            CREATE INDEX IF NOT EXISTS idx_cells_file ON cells(file_path);
        """)
        self._conn.commit()

    def is_unchanged(self, path: str, checksum: str) -> bool:
        row = self._conn.execute(
            "SELECT checksum FROM files WHERE path = ?", (path,)
        ).fetchone()
        return row is not None and row[0] == checksum

    def save_file(self, path: str, checksum: str, size: int, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO files (path, checksum, size, processed_at, session_id) VALUES (?, ?, ?, ?, ?)",
                (path, checksum, size, time.strftime("%Y-%m-%dT%H:%M:%S"), session_id),
            )
            self._conn.commit()

    def save_results(self, session_id: str, cells: list[Cell], cards: list) -> None:
        with self._lock:
            for cell in cells:
                span = None
                if cell.source and cell.source.span:
                    span = json.dumps({"start": cell.source.span.start, "end": cell.source.span.end})
                meta = json.dumps(cell.metadata) if cell.metadata else None
                fp = cell.source.resource_path if cell.source else ""
                try:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO cells (id, file_path, content_type, body, source_span, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                        (cell.id, fp, cell.content_type.name, cell.body[:5000] if isinstance(cell.body, str) else str(cell.body)[:5000], span, meta),
                    )
                except Exception:
                    pass
            for card in cards:
                try:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO cards (id, cell_id, session_id, schema_id, fields, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                        (card.source_cell_id + ":card", card.source_cell_id, session_id, card.schema_id, json.dumps(card.fields), card.confidence),
                    )
                except Exception:
                    pass
            self._conn.commit()

    def search_cards(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM cards WHERE fields LIKE ? ORDER BY rowid DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        results = []
        for row in rows:
            try:
                fields = json.loads(row["fields"])
            except Exception:
                fields = {}
            results.append({
                "cell_id": row["cell_id"],
                "session_id": row["session_id"],
                "schema_id": row["schema_id"],
                "fields": {k: v for k, v in fields.items() if v},
                "confidence": row["confidence"],
            })
        return results

    def get_all_sessions(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT session_id FROM files ORDER BY processed_at DESC"
        ).fetchall()
        return [r["session_id"] for r in rows]

    def close(self) -> None:
        self._conn.close()


def checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# FileWatcher — polling directory monitor
# ---------------------------------------------------------------------------


class FileWatcher:
    """Poll a directory for new/changed files and auto-process them.

    Args:
        watch_dir: Directory to monitor.
        db: PipelineDB instance for persistence.
        schema_registry: SchemaRegistry with registered templates.
        template_id: Default schema template to use.
        mode: Extraction mode ("mock", "ollama", "instructor", "json").
        model: Model name for extraction.
        api_base: API base URL for model.
        interval: Polling interval in seconds.

    Usage::

        db = PipelineDB("index.db")
        watcher = FileWatcher("./docs", db, registry, template_id="paper")
        watcher.start()
        # ... later
        watcher.stop()
    """

    def __init__(
        self,
        watch_dir: str,
        db: PipelineDB,
        schema_registry: SchemaRegistry,
        template_id: str = "paper",
        mode: str = "mock",
        model: str = "gpt-4o-mini",
        api_base: str | None = None,
        interval: int = 30,
    ):
        self._watch_dir = Path(watch_dir).resolve()
        self._db = db
        self._registry = schema_registry
        self._template_id = template_id
        self._mode = mode
        self._model = model
        self._api_base = api_base
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("FileWatcher started: %s (interval=%ds)", self._watch_dir, self._interval)

    def stop(self) -> None:
        self._running = False
        logger.info("FileWatcher stopped")

    def _run(self) -> None:
        while self._running:
            self._scan()
            time.sleep(self._interval)

    def _scan(self) -> None:
        if not self._watch_dir.exists():
            return
        for f in sorted(self._watch_dir.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            chk = checksum(str(f))
            if self._db.is_unchanged(str(f), chk):
                continue
            try:
                self._process_file(str(f), chk, f.stat().st_size)
            except Exception as e:
                logger.warning("Error processing %s: %s", f, e)

    def _process_file(self, path: str, chk: str, size: int) -> None:
        import asyncio
        session_id = f"watch_{Path(path).stem}_{int(time.time())}"

        # Create a fresh pipeline
        pipeline = DataPipeline()
        pipeline.add_default_adapters()
        pipeline.toolchain.add_tool(SemanticSplitter(max_chars=1000, overlap_chars=100))
        pipeline.toolchain.add_tool(RelationBuilder(strategy="keyword_overlap", min_overlap=2))
        pipeline.with_schema_extractor(
            self._registry, template_id=self._template_id,
            mode=self._mode, model=self._model, api_base=self._api_base,
        )

        # Read file
        hint = SUPPORTED_EXTENSIONS.get(Path(path).suffix.lower(), "unknown")
        ref = ResourceRef(connector="fs", resource_path=path, content_type_hint=hint)
        with open(path, "rb") as f:
            raw = f.read()

        # Run pipeline
        kp = asyncio.run(pipeline.run_raw(ref, raw))

        # Persist
        self._db.save_file(path, chk, size, session_id)
        # We don't have direct access to the raw cells from KnowledgePackage
        # Save what we have (cards)
        self._db.save_results(session_id, [], kp.cards)
        logger.info("Processed %s: %d cards (session=%s)", Path(path).name, len(kp.cards), session_id)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LitePaperReader File Watcher")
    parser.add_argument("--watch-dir", required=True, help="Directory to monitor")
    parser.add_argument("--db", default="litepaper_index.db", help="SQLite database path")
    parser.add_argument("--template", default="paper", help="Schema template ID")
    parser.add_argument("--mode", default="mock", help="Extraction mode (mock/ollama/instructor/json)")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model name")
    parser.add_argument("--api-base", help="API base URL (for Ollama/OpenAI)")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds")
    parser.add_argument("--oneshot", action="store_true", help="Process once and exit (no polling)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    db = PipelineDB(args.db)
    watcher = FileWatcher(
        watch_dir=args.watch_dir,
        db=db,
        schema_registry=_default_registry,
        template_id=args.template,
        mode=args.mode,
        model=args.model,
        api_base=args.api_base,
        interval=args.interval,
    )

    if args.oneshot:
        watcher._scan()
        logger.info("Oneshot scan complete. Processed new files into %s", args.db)
    else:
        logger.info("Watching %s (poll every %ds)...", args.watch_dir, args.interval)
        watcher.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
            logger.info("Shutdown")


if __name__ == "__main__":
    main()
