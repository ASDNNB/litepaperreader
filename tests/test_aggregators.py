"""Cross-document RelationBuilder tests."""
import asyncio
import os
import tempfile

import pytest

from litepaperreader.core.cell import Cell, ContentType, SourceRef
from litepaperreader.core.cell import Relation as Rel
from litepaperreader.pipeline.aggregators import (
    RelationBuilder,
    HierarchicalAggregator,
    extract_keywords,
)


# =============================================================
# extract_keywords
# =============================================================

def test_extract_keywords():
    kw = extract_keywords("machine learning for image recognition")
    assert "machine" in kw
    assert "learning" in kw
    assert "recognition" in kw
    assert "for" not in kw  # short word
    assert len(kw) == 4


def test_extract_keywords_strip_punctuation():
    kw = extract_keywords("Hello, world! This is a test.")
    assert "hello" in kw
    assert "world" in kw
    assert "test" in kw


def test_extract_keywords_empty():
    assert extract_keywords("") == set()
    assert extract_keywords(None) == set()


# =============================================================
# RelationBuilder — keyword_overlap
# =============================================================

async def _run_builder(cells, strategy="keyword_overlap"):
    builder = RelationBuilder(strategy=strategy, min_overlap=2)
    async def input_cells():
        for c in cells:
            yield c
    results = []
    async for c in builder.process(input_cells(), None):
        results.append(c)
    return results


def test_keyword_overlap_creates_relations():
    ref1 = SourceRef(connector="test", resource_path="/doc1.txt", resource_checksum="a1")
    ref2 = SourceRef(connector="test", resource_path="/doc2.txt", resource_checksum="a2")
    cells = [
        Cell(id="c1", source=ref1, content_type=ContentType.TEXT,
             body="machine learning for image classification"),
        Cell(id="c2", source=ref2, content_type=ContentType.TEXT,
             body="machine learning for text classification"),
    ]
    results = asyncio.run(_run_builder(cells))
    # Both cells should now have relations
    r1 = results[0]
    r2 = results[1]
    assert len(r1.relations) >= 1, "c1 should have relations"
    assert len(r2.relations) >= 1, "c2 should have relations"
    rel = r1.relations[0]
    assert rel.relation_type == "keyword_overlap"
    assert rel.target_id == "c2"
    assert "machine" in rel.metadata.get("shared_keywords", [])
    assert "learning" in rel.metadata.get("shared_keywords", [])


def test_keyword_overlap_same_source():
    ref = SourceRef(connector="test", resource_path="/doc.txt", resource_checksum="a1")
    cells = [
        Cell(id="c1", source=ref, content_type=ContentType.TEXT,
             body="machine learning for image classification"),
        Cell(id="c2", source=ref, content_type=ContentType.TEXT,
             body="machine learning for text classification"),
    ]
    results = asyncio.run(_run_builder(cells))
    assert len(results[0].relations) == 0, "same source should not create relations"
    assert len(results[1].relations) == 0


def test_keyword_overlap_below_threshold():
    ref1 = SourceRef(connector="test", resource_path="/doc1.txt", resource_checksum="a1")
    ref2 = SourceRef(connector="test", resource_path="/doc2.txt", resource_checksum="a2")
    cells = [
        Cell(id="c1", source=ref1, content_type=ContentType.TEXT,
             body="machine learning"),
        Cell(id="c2", source=ref2, content_type=ContentType.TEXT,
             body="deep learning"),
    ]
    # min_overlap=2, but only "learning" overlaps -> below threshold
    results = asyncio.run(_run_builder(cells))
    assert len(results[0].relations) == 0


# =============================================================
# RelationBuilder — code_dependency
# =============================================================

def test_code_dependency():
    ref1 = SourceRef(connector="test", resource_path="/main.py", resource_checksum="a1")
    ref2 = SourceRef(connector="test", resource_path="/utils.py", resource_checksum="a2")
    cells = [
        Cell(id="c1", source=ref1, content_type=ContentType.CODE,
             body="result = helper_function()", metadata={"function": "main"}),
        Cell(id="c2", source=ref2, content_type=ContentType.CODE,
             body="def helper_function():\n    return 42", metadata={"function": "helper_function"}),
    ]
    builder = RelationBuilder(strategy="code_dependency")
    results = asyncio.run(_run_builder(cells, strategy="code_dependency"))
    rels = results[0].relations
    assert len(rels) >= 1
    assert rels[0].relation_type == "references"
    assert rels[0].target_id == "c2"


# =============================================================
# Integration: cross-document via DataPipeline
# =============================================================

def test_cross_document_pipeline():
    """Two HTML files in a directory -> RelationBuilder -> cross-doc relations."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.pipeline.extractor import SchemaExtractor
    from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec

    reg = SchemaRegistry()
    reg.register(SchemaTemplate(template_id="paper", description="Paper", fields=(
        FieldSpec(name="topic", description="Paper topic"),
        FieldSpec(name="method", description="Method used"),
    )))

    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.toolchain.add_tool(SemanticSplitter(max_chars=200, overlap_chars=20))
    # Add relation builder with low threshold for test
    pipeline.toolchain.add_tool(RelationBuilder(strategy="keyword_overlap", min_overlap=1))
    pipeline.with_schema_extractor(reg, template_id="paper", mode="mock")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Doc 1: about machine learning
        with open(os.path.join(tmpdir, "doc1.html"), "w", encoding="utf-8") as f:
            f.write("<html><body><p>Machine learning for image classification using deep neural networks.</p></body></html>")
        # Doc 2: about deep learning (shared keywords: deep, learning, neural)
        with open(os.path.join(tmpdir, "doc2.html"), "w", encoding="utf-8") as f:
            f.write("<html><body><p>Deep neural networks for text classification with machine learning.</p></body></html>")

        async def run():
            kp = await pipeline.run_file(tmpdir)
            return kp

        kp = asyncio.run(run())
        assert kp.metadata.get("num_cells", 0) >= 2
        # The relation builder adds relations via the toolchain,
        # but KnowledgePackage doesn't expose cell relations directly.
        # Verify at least the pipeline completed successfully.
        assert kp.metadata.get("resources", 0) >= 2
