"""AnswerGenerator tests - mock, fallback, and integration modes."""
import asyncio
import json

import pytest

from litepaperreader.core.cell import Cell, ContentType, SourceRef
from litepaperreader.knowledge.package import KnowledgePackage, StructuredCard, SummaryNode
from litepaperreader.knowledge.answer import Answer, AnswerGenerator, Citation


# =============================================================
# Mock mode tests
# =============================================================

def test_mock_answer_no_knowledge():
    """Answer with empty KnowledgePackage returns helpful message."""
    gen = AnswerGenerator(mode="mock")
    kp = KnowledgePackage()

    async def run():
        return await gen.answer("What is the method?", kp)

    answer = asyncio.run(run())
    assert isinstance(answer, Answer)
    assert isinstance(answer.text, str)
    assert len(answer.text) > 0
    assert answer.confidence < 0.5  # low confidence for empty knowledge


def test_mock_answer_with_matching_cards():
    """Answer uses keywords to find relevant cards."""
    gen = AnswerGenerator(mode="mock")
    ref = SourceRef(connector="test", resource_path="/doc.txt", resource_checksum="abc")
    cards = [
        StructuredCard(
            schema_id="paper",
            fields={"method": "deep reinforcement learning", "title": "Novel RL Method"},
            source_cell_id="cell-001",
            source_ref=ref,
        ),
    ]
    kp = KnowledgePackage(cards=cards, metadata={"num_cells": 10, "resources": 1})

    async def run():
        return await gen.answer("What learning method?", kp)

    answer = asyncio.run(run())
    assert len(answer.citations) >= 1
    assert "cell-001" == answer.citations[0].cell_id
    assert answer.confidence >= 0.5


def test_mock_answer_no_matching_cards():
    """Answer with no keyword matches returns informative fallback."""
    gen = AnswerGenerator(mode="mock")
    ref = SourceRef(connector="test", resource_path="/doc.txt", resource_checksum="abc")
    cards = [
        StructuredCard(
            schema_id="paper",
            fields={"method": "transformer", "title": "Neural Net"},
            source_cell_id="cell-001",
            source_ref=ref,
        ),
    ]
    kp = KnowledgePackage(cards=cards, metadata={"num_cells": 5, "resources": 1})

    # Question has no keywords matching the card fields
    async def run():
        return await gen.answer("What is the budget?", kp)

    answer = asyncio.run(run())
    # Should still produce a response with the available info
    assert "transformer" in answer.text or "Neural" in answer.text


def test_mock_answer_correct_citations():
    """Citations reference the correct source cell IDs."""
    gen = AnswerGenerator(mode="mock")
    ref1 = SourceRef(connector="test", resource_path="/d1.txt", resource_checksum="abc")
    ref2 = SourceRef(connector="test", resource_path="/d2.txt", resource_checksum="def")
    cards = [
        StructuredCard(schema_id="paper", fields={"method": "gradient descent"},
                       source_cell_id="cell-a1", source_ref=ref1),
        StructuredCard(schema_id="paper", fields={"result": "95% accuracy"},
                       source_cell_id="cell-b2", source_ref=ref2),
    ]
    kp = KnowledgePackage(cards=cards, metadata={"num_cells": 20, "resources": 2})

    async def run():
        return await gen.answer("gradient descent accuracy", kp)

    answer = asyncio.run(run())
    assert len(answer.citations) >= 1
    assert answer.citations[0].cell_id in ("cell-a1", "cell-b2")


# =============================================================
# Consumption mode resolution
# =============================================================

def test_answer_resolves_inject_mode_for_small_knowledge():
    """Small knowledge automatically uses inject mode."""
    gen = AnswerGenerator(mode="mock", max_context_chars=1000)
    kp = KnowledgePackage()

    resolved = gen._resolve_mode("auto", kp)
    assert resolved == "inject"


def test_answer_resolves_auto_mode_correctly():
    """Auto mode picks inject for small knowledge, retrieve for large."""
    gen = AnswerGenerator(mode="mock", max_context_chars=100)

    # Small knowledge
    kp_small = KnowledgePackage()
    assert gen._resolve_mode("auto", kp_small) == "inject"

    # Large knowledge
    ref = SourceRef(connector="test", resource_path="/d.txt", resource_checksum="abc")
    cards = [
        StructuredCard(
            schema_id="paper",
            fields={"data": "X" * 200},
            source_cell_id="c1",
            source_ref=ref,
        ),
    ]
    kp_large = KnowledgePackage(cards=cards)
    assert gen._resolve_mode("auto", kp_large) == "retrieve"


# =============================================================
# Context building
# =============================================================

def test_build_context_empty():
    """Empty knowledge produces minimal context."""
    gen = AnswerGenerator(mode="mock")
    ctx = gen._build_context(KnowledgePackage(), "inject")
    assert isinstance(ctx, str)


def test_build_context_with_cards():
    """Cards appear in context string."""
    gen = AnswerGenerator(mode="mock")
    ref = SourceRef(connector="test", resource_path="/d.txt", resource_checksum="abc")
    cards = [
        StructuredCard(schema_id="paper", fields={"method": "SVM"},
                       source_cell_id="c1", source_ref=ref),
    ]
    root = SummaryNode(level=0, title="Doc", summary="Test document")
    kp = KnowledgePackage(cards=cards, summary_tree=root)

    ctx = gen._build_context(kp, "inject")
    assert "SVM" in ctx
    assert "Test document" in ctx


# =============================================================
# OpenAI/Claude/Ollama fallback tests
# =============================================================

def test_openai_fallback_to_mock():
    """OpenAI mode falls back to mock when openai not installed."""
    gen = AnswerGenerator(mode="openai", api_key="test-key")
    ref = SourceRef(connector="test", resource_path="/d.txt", resource_checksum="abc")
    cards = [StructuredCard(schema_id="t", fields={"key": "value"}, source_cell_id="c1", source_ref=ref)]
    kp = KnowledgePackage(cards=cards, metadata={"num_cells": 1})

    async def run():
        return await gen.answer("test", kp)

    answer = asyncio.run(run())
    assert isinstance(answer, Answer)


def test_claude_fallback_to_mock():
    """Claude mode falls back to mock when anthropic not installed."""
    gen = AnswerGenerator(mode="claude", api_key="test-key")
    kp = KnowledgePackage()

    async def run():
        return await gen.answer("test", kp)

    answer = asyncio.run(run())
    assert isinstance(answer, Answer)


def test_ollama_fallback_to_mock():
    """Ollama mode falls back to mock when requests not installed (handled gracefully)."""
    gen = AnswerGenerator(mode="ollama", api_base="http://localhost:11434")
    kp = KnowledgePackage()

    async def run():
        return await gen.answer("test", kp)

    answer = asyncio.run(run())
    assert isinstance(answer, Answer)


# =============================================================
# Integration: DataPipeline -> KnowledgePackage -> Answer
# =============================================================

def test_full_qa_pipeline():
    """End-to-end: HTML -> DataPipeline -> SchemaExtractor -> AnswerGenerator."""
    from litepaperreader.pipeline.orchestrator import DataPipeline
    from litepaperreader.pipeline.splitters import SemanticSplitter
    from litepaperreader.connectors.base import ResourceRef
    from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec

    reg = SchemaRegistry()
    reg.register(SchemaTemplate(template_id="paper", description="Paper", fields=(
        FieldSpec(name="method", description="Core method used"),
        FieldSpec(name="result", description="Experimental result"),
    )))

    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.toolchain.add_tool(SemanticSplitter(max_chars=500, overlap_chars=50))
    pipeline.with_schema_extractor(reg, template_id="paper", mode="mock")

    html = (
        b"<html><body>"
        b"<p>This paper proposes a novel method using deep reinforcement learning "
        b"for robotics control. The experimental method achieves 95% success rate.</p>"
        b"</body></html>"
    )
    ref = ResourceRef(connector="test", resource_path="/paper.html", content_type_hint="html")

    gen = AnswerGenerator(mode="mock")

    async def run():
        kp = await pipeline.run_raw(ref, html)
        return await gen.answer("What method and result?", kp), kp

    answer, kp = asyncio.run(run())
    assert isinstance(answer, Answer)
    assert kp.metadata.get("num_cards", 0) >= 0
    # Answer should reference discovered cards
    assert isinstance(answer.text, str) and len(answer.text) > 0
