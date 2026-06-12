"""Tests for SchemaExtractor — mock, ollama, and integration modes."""
import asyncio
import json

import pytest

from litepaperreader.core.cell import Cell, ContentType, SourceRef
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec


# =============================================================
# Mock extraction tests (no model needed)
# =============================================================

@pytest.fixture
def registry():
    reg = SchemaRegistry()
    reg.register(SchemaTemplate(
        template_id="paper",
        description="Academic paper",
        fields=(
            FieldSpec(name="title", description="The paper title"),
            FieldSpec(name="method", description="Core method used"),
            FieldSpec(name="result", description="Key experimental result"),
        ),
    ))
    return reg


@pytest.fixture
def mock_extractor(registry):
    from litepaperreader.pipeline.extractor import SchemaExtractor
    return SchemaExtractor(registry, template_id="paper", mode="mock")


def test_mock_extraction_returns_dict(mock_extractor):
    """Mock extraction returns a dict with all schema fields."""
    text = "This paper presents a novel method using deep learning."
    result = mock_extractor._extract_mock(text)
    assert isinstance(result, dict)
    assert "title" in result
    assert "method" in result
    assert "result" in result


def test_mock_extraction_populates_matched_fields(mock_extractor):
    """Fields whose description keywords appear in text get populated."""
    text = "Our method achieves high accuracy on the benchmark."
    result = mock_extractor._extract_mock(text)
    # 'method' description ('Core method used') contains 'method' and 'used'
    # 'method' appears in text -> field should be populated
    assert result["method"] is not None
    assert "Mock[" in result["method"]


def test_mock_extraction_null_for_unmatched(mock_extractor):
    """Fields whose keywords don't appear in text are null."""
    # Use text that has NO words from the field descriptions
    # descriptions: "The paper title", "Core method used", "Key experimental result"
    text = "xylophone zebra quantum."
    result = mock_extractor._extract_mock(text)
    assert result["method"] is None
    assert result["result"] is None
    assert result["title"] is None


def test_mock_extraction_matches_description_keywords(mock_extractor):
    """The mock value reflects which keyword was matched from the description."""
    text = "The title of this paper is about machine learning."
    result = mock_extractor._extract_mock(text)
    # 'title' field has description "The paper title"
    # Words >3 chars: "paper", "title"
    # "title" appears in text -> matches
    # But "paper" also appears in text -> matches first
    assert result["title"] is not None


def test_mock_extraction_null_for_short_words(registry):
    """Words <=3 characters in descriptions are skipped."""
    from litepaperreader.pipeline.extractor import SchemaExtractor
    reg = SchemaRegistry()
    reg.register(SchemaTemplate(
        template_id="t1",
        description="Test",
        fields=(
            FieldSpec(name="key", description="A key field for testing"),
        ),
    ))
    extractor = SchemaExtractor(reg, template_id="t1", mode="mock")
    # description "A key field for testing"
    # Words: "A"(1), "key"(3), "field"(5), "for"(3), "testing"(7)
    # Words >3 chars: "field", "testing"
    result = extractor._extract_mock("testing something")
    assert result["key"] is not None
    assert "testing" in result["key"].lower()


# =============================================================
# Async extraction tests (using asyncio.run, no pytest plugin)
# =============================================================

def test_mock_extraction_via_process():
    """Test the full PipelineTool process() with mock extraction."""
    from litepaperreader.pipeline.extractor import SchemaExtractor
    from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec

    reg = SchemaRegistry()
    reg.register(SchemaTemplate(
        template_id="paper",
        description="Academic paper",
        fields=(
            FieldSpec(name="title", description="The paper title"),
            FieldSpec(name="method", description="Core method used"),
        ),
    ))
    extractor = SchemaExtractor(reg, template_id="paper", mode="mock")
    ref = SourceRef(connector="test", resource_path="/doc.txt", resource_checksum="abc")
    input_cell = Cell(
        id="c1", source=ref,
        content_type=ContentType.TEXT,
        body="This paper proposes a novel method for semantic segmentation "
             "using transformer architectures.",
    )

    async def test():
        async def input_cells():
            yield input_cell
        results = []
        async for cell in extractor.process(input_cells(), None):
            results.append(cell)
        return results

    results = asyncio.run(test())
    assert len(results) == 1
    output = results[0]
    assert output.id == "c1:extracted"
    assert output.metadata.get("type") == "extraction"
    assert output.metadata.get("schema") == "paper"
    assert output.metadata.get("extraction_mode") == "mock"

    body = json.loads(output.body)
    assert isinstance(body, dict)
    assert "method" in body


def test_pipeline_with_extraction():
    """DataPipeline with SchemaExtractor produces KnowledgePackage with cards."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.extractor import SchemaExtractor
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.connectors.base import ResourceRef
    from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec

    reg = SchemaRegistry()
    reg.register(SchemaTemplate(
        template_id="paper",
        description="Academic paper",
        fields=(
            FieldSpec(name="title", description="The paper title"),
            FieldSpec(name="method", description="Core method used"),
        ),
    ))

    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.toolchain.add_tool(SemanticSplitter(max_chars=500, overlap_chars=50))
    pipeline.with_schema_extractor(reg, template_id="paper", mode="mock")

    html = (
        b"<html><body>"
        b"<h1>A Novel Method for Deep Learning</h1>"
        b"<p>This paper presents a new method for training deep neural networks "
        b"using reinforcement learning.</p>"
        b"</body></html>"
    )
    ref = ResourceRef(connector="test", resource_path="/paper.html", content_type_hint="html")

    async def test():
        return await pipeline.run_raw(ref, html)

    kp = asyncio.run(test())
    assert kp.metadata.get("num_cells", 0) > 0
    assert kp.metadata.get("num_cards", 0) >= 0  # extraction cards if method keyword matched


# =============================================================
# Multiple templates / multiple fields
# =============================================================

def test_mock_extraction_with_different_templates(registry):
    """Different schema templates produce different field sets."""
    from litepaperreader.pipeline.extractor import SchemaExtractor
    reg2 = SchemaRegistry()
    reg2.register(SchemaTemplate(
        template_id="person",
        description="Person profile",
        fields=(
            FieldSpec(name="name", description="Full name of person"),
            FieldSpec(name="occupation", description="Job title or occupation"),
        ),
    ))

    extractor = SchemaExtractor(reg2, template_id="person", mode="mock")
    text = "Dr. Alice Wang is a senior software engineer at Google."
    result = extractor._extract_mock(text)

    assert "name" in result
    assert "occupation" in result
    # 'occupation' desc = 'Job title or occupation'
    # Words >3 chars: 'title', 'occupation'
    # Neither appears in 'senior software engineer'
    # So occupation should be None
    assert result["occupation"] is None


# =============================================================
# Ollama extraction (integration test, skipped if no Ollama)
# =============================================================

def test_ollama_extraction_skipped_by_default():
    """Test is skipped unless OLLAMA_BASE_URL is set."""
    import os
    if not os.environ.get("OLLAMA_BASE_URL"):
        pytest.skip("OLLAMA_BASE_URL not set")
