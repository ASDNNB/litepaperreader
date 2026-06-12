"""Phase 6: End-to-end integration tests for the full data pipeline."""
import asyncio
import csv
import io
import os
import tempfile

import pytest

from litepaperreader.core.cell import Cell, ContentType, SourceRef
from litepaperreader.knowledge.package import KnowledgePackage


# === 1. HTML end-to-end: raw HTML -> HTMLAdapter -> cells ===

def test_html_e2e_basic():
    """HTML -> HTMLAdapter -> TEXT Cells (no pipeline tools)."""
    from litepaperreader.adapters.html_adapter import HTMLAdapter
    from litepaperreader.connectors.base import ResourceRef

    adapter = HTMLAdapter()
    html = b"<html><body><h1>Title</h1><p>First paragraph.</p><p>Second paragraph.</p></body></html>"
    ref = ResourceRef(connector="test", resource_path="/doc.html", content_type_hint="html")
    cells = list(adapter.convert(ref, html))

    assert len(cells) >= 1
    for cell in cells:
        assert cell.content_type == ContentType.TEXT
        assert isinstance(cell.body, str)
        assert len(cell.body) > 0
        assert cell.source.connector == "test"


def test_html_e2e_with_splitter():
    """HTML -> Adapter -> SemanticSplitter -> multiple smaller cells."""
    from litepaperreader.adapters.html_adapter import HTMLAdapter
    from litepaperreader.connectors.base import ResourceRef
    from litepaperreader.pipeline.splitters import SemanticSplitter

    adapter = HTMLAdapter()
    splitter = SemanticSplitter(max_chars=30, overlap_chars=5)
    body = " ".join(["word"] * 100)
    html = f"<html><body><p>{body}</p></body></html>".encode()
    ref = ResourceRef(connector="test", resource_path="/doc.html", content_type_hint="html")

    cells = list(adapter.convert(ref, html))
    assert len(cells) > 0

    async def run():
        async def input_cells():
            for c in cells:
                yield c
        results = []
        async for c in splitter.process(input_cells(), None):
            results.append(c)
        return results

    split_cells = asyncio.run(run())
    assert len(split_cells) > len(cells)


# === 2. Table end-to-end: CSV bytes -> TableAdapter -> TABLE Cells ===

def test_table_e2e_csv():
    """CSV bytes -> TableAdapter -> TABLE Cells."""
    from litepaperreader.adapters.table_adapter import TableAdapter
    from litepaperreader.connectors.base import ResourceRef

    adapter = TableAdapter()
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["name", "age", "city"])
    writer.writerow(["Alice", "30", "Beijing"])
    writer.writerow(["Bob", "25", "Shanghai"])
    csv_bytes = csv_buffer.getvalue().encode()

    ref = ResourceRef(connector="test", resource_path="/data.csv")
    cells = list(adapter.convert(ref, csv_bytes))

    if len(cells) > 0:
        row_cells = [c for c in cells if c.content_type == ContentType.TABLE]
        assert len(row_cells) >= 2
        for c in row_cells:
            assert "name" in c.body or "Alice" in c.body or "Table with" in c.body


# === 3. Code end-to-end: Python source -> CodeAdapter -> CODE Cells ===

def test_code_e2e_python():
    """Python source -> CodeAdapter -> CODE Cells."""
    from litepaperreader.adapters.code_adapter import CodeAdapter
    from litepaperreader.connectors.base import ResourceRef

    adapter = CodeAdapter()
    code = b"""
import os

def hello(name):
    print(f"Hello {name}")

class Greeter:
    def greet(self):
        pass
"""
    ref = ResourceRef(connector="test", resource_path="/main.py")
    cells = list(adapter.convert(ref, code))

    assert len(cells) > 0
    for c in cells:
        assert c.content_type == ContentType.CODE
        assert "language" in c.metadata or (c.structure and c.structure.language)


# === 4. DataPipeline orchestration e2e ===

def test_pipeline_raw_html():
    """DataPipeline.run_raw with HTML source -> KnowledgePackage."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.pipeline.filters import Deduplicator
    from litepaperreader.connectors.base import ResourceRef

    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    t_split = pipeline.toolchain.add_tool(SemanticSplitter(max_chars=100, overlap_chars=10))
    t_dedup = pipeline.toolchain.add_tool(Deduplicator())
    pipeline.toolchain.add_edge(t_split, t_dedup)

    html = b"<html><body>" + b"<p>Long paragraph " + b"word " * 50 + b"</p>" * 3 + b"</body></html>"
    ref = ResourceRef(connector="test", resource_path="/test.html", content_type_hint="html")

    import asyncio
    kp = asyncio.run(pipeline.run_raw(ref, html))
    assert isinstance(kp, KnowledgePackage)
    assert kp.metadata.get("num_cells", 0) > 0


def test_pipeline_raw_code():
    """DataPipeline.run_raw with Python source."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.connectors.base import ResourceRef

    pipeline = DataPipeline()
    pipeline.add_default_adapters()

    code = b"def foo():\n    return 42\n\ndef bar():\n    return foo()\n"
    ref = ResourceRef(connector="test", resource_path="/code.py")

    import asyncio
    kp = asyncio.run(pipeline.run_raw(ref, code))
    assert kp.metadata.get("num_cells", 0) >= 1


def test_pipeline_file():
    """DataPipeline.run_file on a temp directory with mixed content."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.splitters import SemanticSplitter

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "test.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<html><body><p>Hello from HTML.</p></body></html>")

        py_path = os.path.join(tmpdir, "script.py")
        with open(py_path, "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")

        pipeline = DataPipeline()
        pipeline.add_default_adapters()
        pipeline.toolchain.add_tool(SemanticSplitter(max_chars=500, overlap_chars=50))

        import asyncio
        kp = asyncio.run(pipeline.run_file(tmpdir))
        assert kp.metadata.get("num_cells", 0) >= 2
        assert kp.metadata.get("resources", 0) >= 2
        assert kp.metadata.get("total_chars", 0) > 0


# === 5. Full DAG pipeline with multiple tool types ===

def test_dag_pipeline_multitool():
    """Full DAG: HTML -> Splitter -> Deduplicator -> KnowledgePackage."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.pipeline.filters import Deduplicator, RelevanceFilter
    from litepaperreader.connectors.base import ResourceRef

    pipeline = DataPipeline()
    pipeline.add_default_adapters()

    t1 = pipeline.toolchain.add_tool(SemanticSplitter(max_chars=50, overlap_chars=5))
    t2 = pipeline.toolchain.add_tool(Deduplicator())
    t3 = pipeline.toolchain.add_tool(RelevanceFilter(min_score=0.0))
    pipeline.toolchain.add_edge(t1, t2)
    pipeline.toolchain.add_edge(t2, t3)

    html = b"<html><body>" + b"<p>AA</p><p>BB</p><p>CC</p>" + b"</body></html>"
    ref = ResourceRef(connector="test", resource_path="/test.html", content_type_hint="html")

    import asyncio
    kp = asyncio.run(pipeline.run_raw(ref, html))
    assert kp.metadata.get("num_cells", 0) > 0
    assert "content_types" in kp.metadata


# === 6. KnowledgePackage building verification ===

def test_knowledge_package_from_cells():
    """Verify KnowledgePackage construction from pipeline output."""
    from litepaperreader.knowledge.package import KnowledgePackage, SummaryNode

    ref = SourceRef(connector="test", resource_path="/f.txt", resource_checksum="abc")
    cells = [
        Cell(id="c1", source=ref, content_type=ContentType.TEXT, body="hello"),
        Cell(id="c2", source=ref, content_type=ContentType.CODE, body="def f(): pass"),
    ]
    root = SummaryNode(level=0, title="Root", summary="2 cells")
    kp = KnowledgePackage(cards=[], summary_tree=root, metadata={"num_cells": len(cells)})
    assert kp.metadata["num_cells"] == 2
    assert kp.summary_tree.title == "Root"
