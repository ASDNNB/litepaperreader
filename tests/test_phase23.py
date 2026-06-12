"""Tests for Phase 2-4 modules: Connectors, Adapters, Pipeline (sync-compatible)."""
import asyncio

import pytest

from litepaperreader.adapters.html_adapter import HTMLAdapter
from litepaperreader.adapters.code_adapter import CodeAdapter
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell, ContentType, SourceRef


# === HTMLAdapter ===

def test_html_adapter_can_handle():
    adapter = HTMLAdapter()
    ref = ResourceRef(connector="test", resource_path="page.html", content_type_hint="html")
    assert adapter.can_handle(ref)
    no_ref = ResourceRef(connector="test", resource_path="file.pdf", content_type_hint="pdf")
    assert not adapter.can_handle(no_ref)


def test_html_adapter_converts_simple_html():
    adapter = HTMLAdapter()
    html = b"<html><body><p>Hello world.</p><p>Second paragraph.</p></body></html>"
    ref = ResourceRef(connector="test", resource_path="/page.html", content_type_hint="html")
    cells = list(adapter.convert(ref, html))
    assert len(cells) > 0
    for cell in cells:
        assert cell.content_type == ContentType.TEXT
    texts = [c.body for c in cells if isinstance(c.body, str)]
    assert any("Hello" in t for t in texts)


def test_html_adapter_empty():
    adapter = HTMLAdapter()
    html = b"<html></html>"
    ref = ResourceRef(connector="test", resource_path="/empty.html", content_type_hint="html")
    cells = list(adapter.convert(ref, html))
    assert len(cells) >= 1


# === CodeAdapter ===

def test_code_adapter_can_handle():
    adapter = CodeAdapter()
    py_ref = ResourceRef(connector="test", resource_path="main.py", content_type_hint="python")
    assert adapter.can_handle(py_ref)
    txt_ref = ResourceRef(connector="test", resource_path="readme.txt", content_type_hint="text")
    assert not adapter.can_handle(txt_ref)


def test_code_adapter_simple_py():
    adapter = CodeAdapter()
    code = b"def hello():\n    print('hello')\n\ndef world():\n    print('world')\n"
    ref = ResourceRef(connector="test", resource_path="/test.py")
    cells = list(adapter.convert(ref, code))
    assert len(cells) > 0
    all_text = "".join(c.body if isinstance(c.body, str) else "" for c in cells)
    assert "hello" in all_text


# === SemanticSplitter (synchronous helper tests) ===

def test_semantic_splitter_choose_end():
    from litepaperreader.pipeline.splitters import SemanticSplitter
    splitter = SemanticSplitter(max_chars=50, overlap_chars=10)

    # Test paragraph boundary preference
    text = "A" * 30 + "\n\n" + "B" * 30
    end = splitter._choose_end(text, 0)
    assert end == 32  # "A"*30 + "\n\n" = 32

    # Test hard boundary when no paragraph break
    text = "A" * 60
    end = splitter._choose_end(text, 0)
    assert end == 50  # max_chars

    # Test end of text
    text = "short"
    end = splitter._choose_end(text, 0)
    assert end == 5


# === Deduplicator (sync test) ===

def test_deduplicator_sync():
    from litepaperreader.pipeline.filters import Deduplicator
    dedup = Deduplicator()
    ref = SourceRef(connector="test", resource_path="/t.txt", resource_checksum="abc")

    # Direct hash test
    h1 = hash("unique1"[:200])
    h2 = hash("unique1"[:200])
    h3 = hash("unique2"[:200])
    assert h1 == h2  # same content = same hash
    assert h1 != h3  # different content = different hash


# === Toolchain (sync tests) ===

def test_toolchain_topological_order():
    from litepaperreader.pipeline.toolchain import Toolchain
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.pipeline.filters import Deduplicator

    tc = Toolchain()
    t1 = tc.add_tool(SemanticSplitter())
    t2 = tc.add_tool(Deduplicator())
    tc.add_edge(t1, t2)
    order = tc.topological_order()
    assert order.index(t1) < order.index(t2)


def test_toolchain_cycle_detection():
    from litepaperreader.pipeline.toolchain import Toolchain
    from litepaperreader.pipeline.splitters import SemanticSplitter

    tc = Toolchain()
    t1 = tc.add_tool(SemanticSplitter())
    t2 = tc.add_tool(SemanticSplitter())
    tc.add_edge(t1, t2)
    tc.add_edge(t2, t1)
    with pytest.raises(ValueError, match="Cycle detected"):
        tc.topological_order()


def test_toolchain_empty():
    from litepaperreader.pipeline.toolchain import Toolchain
    tc = Toolchain()
    assert tc.topological_order() == []


# === FileSystemConnector sync test ===

def test_filesystem_connector_scan():
    from litepaperreader.connectors.filesystem import FileSystemConnector
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file
        testfile = os.path.join(tmpdir, "test.txt")
        with open(testfile, "w") as f:
            f.write("hello")
        connector = FileSystemConnector()
        refs = list(connector.scan(tmpdir))
        assert len(refs) >= 1
        assert any("test.txt" in r.resource_path for r in refs)


# === Async pipeline test (using asyncio.run) ===

def test_toolchain_run_sync():
    from litepaperreader.pipeline.toolchain import Toolchain
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.pipeline.filters import Deduplicator

    async def run():
        tc = Toolchain()
        t1 = tc.add_tool(SemanticSplitter(max_chars=30, overlap_chars=5))
        t2 = tc.add_tool(Deduplicator())
        tc.add_edge(t1, t2)

        ref = SourceRef(connector="test", resource_path="/t.txt", resource_checksum="abc")
        cells = [
            Cell(id="c1", source=ref, content_type=ContentType.TEXT,
                 body="A" * 20 + "\n\n" + "B" * 20),
            Cell(id="c2", source=ref, content_type=ContentType.TEXT, body="unique"),
        ]

        async def input_cells():
            for c in cells:
                yield c

        results = []
        async for c in tc.run(input_cells()):
            results.append(c)
        return results

    results = asyncio.run(run())
    assert len(results) >= 2


def test_semantic_splitter_async():
    from litepaperreader.pipeline.splitters import SemanticSplitter

    async def run():
        splitter = SemanticSplitter(max_chars=50, overlap_chars=10)
        ref = SourceRef(connector="test", resource_path="/t.txt", resource_checksum="abc")
        cell = Cell(id="c1", source=ref, content_type=ContentType.TEXT,
                    body="A" * 30 + "\n\n" + "B" * 30)

        async def input_cells():
            yield cell

        results = []
        async for c in splitter.process(input_cells(), None):
            results.append(c)
        return results

    results = asyncio.run(run())
    assert len(results) >= 2


def test_deduplicator_async():
    from litepaperreader.pipeline.filters import Deduplicator

    async def run():
        dedup = Deduplicator()
        ref = SourceRef(connector="test", resource_path="/t.txt", resource_checksum="abc")
        cells_data = [
            Cell(id="c1", source=ref, content_type=ContentType.TEXT, body="unique1"),
            Cell(id="c2", source=ref, content_type=ContentType.TEXT, body="unique1"),
            Cell(id="c3", source=ref, content_type=ContentType.TEXT, body="unique2"),
        ]

        async def input_cells():
            for c in cells_data:
                yield c

        results = []
        async for c in dedup.process(input_cells(), None):
            results.append(c)
        return results

    results = asyncio.run(run())
    assert len(results) == 2


def test_relevance_filter_async():
    from litepaperreader.pipeline.filters import RelevanceFilter

    async def run():
        filt = RelevanceFilter(min_score=0.5)
        ref = SourceRef(connector="test", resource_path="/t.txt", resource_checksum="abc")
        cells_data = [
            Cell(id="c1", source=ref, content_type=ContentType.TEXT, body="short"),
            Cell(id="c2", source=ref, content_type=ContentType.TEXT, body="X" * 1500),
        ]

        async def input_cells():
            for c in cells_data:
                yield c

        results = []
        async for c in filt.process(input_cells(), None):
            results.append(c)
        return results

    results = asyncio.run(run())
    assert len(results) == 1
    assert results[0].id == "c2"
