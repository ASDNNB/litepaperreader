"""Cell aggregators and cross-document RelationBuilder."""
from __future__ import annotations

import logging
from typing import AsyncIterator

from litepaperreader.core.cell import Cell, ContentType, Relation
from litepaperreader.pipeline.tool import PipelineTool, ToolContext

logger = logging.getLogger(__name__)

DEFAULT_STOP_WORDS: set[str] = {
    "this", "that", "with", "from", "they", "have", "been",
    "will", "were", "what", "when", "where", "which", "their",
    "them", "than", "then", "just", "also", "can", "has",
    "about", "into", "over", "such", "only", "other", "more",
    "some", "these", "those", "very", "after", "before",
}


def extract_keywords(text: str, stop_words: set[str] | None = None) -> set[str]:
    if not text:
        return set()
    stop = stop_words or DEFAULT_STOP_WORDS
    words = text.lower().split()
    return {
        w.strip('.,;:!?()[]"'"'"'`')
        for w in words
        if len(w) > 3 and w not in stop
    }


class RelationBuilder(PipelineTool):
    """Build relationships between Cells, especially across documents.

    Strategies
    ---------
    keyword_overlap
        Find pairs of cells from different source resources that share
        multiple significant keywords.
    code_dependency
        Find function/class name references between CODE cells.
    """

    name = "relation_builder"
    input_types: set[ContentType] | None = None

    def __init__(
        self,
        strategy: str = "keyword_overlap",
        min_overlap: int = 3,
        stop_words: set[str] | None = None,
    ):
        self.strategy = strategy
        self.min_overlap = min_overlap
        self.stop_words = stop_words or DEFAULT_STOP_WORDS

    async def process(
        self, cells: AsyncIterator[Cell], ctx: ToolContext
    ) -> AsyncIterator[Cell]:
        all_cells: list[Cell] = []
        async for cell in cells:
            all_cells.append(cell)

        if len(all_cells) < 2:
            for cell in all_cells:
                yield cell
            return

        if self.strategy == "keyword_overlap":
            self._build_keyword_overlap(all_cells)
        elif self.strategy == "code_dependency":
            self._build_code_dependency(all_cells)
        elif self.strategy == "entity_cooccurrence":
            self._build_entity_cooccurrence(all_cells)
        elif self.strategy == "citation":
            self._build_citation_links(all_cells)
        else:
            logger.warning("Unknown strategy: %s", self.strategy)

        for cell in all_cells:
            yield cell

    def _build_keyword_overlap(self, cells: list[Cell]) -> None:
        kw_cache: dict[str, set[str]] = {}
        for c in cells:
            text = c.body if isinstance(c.body, str) else ""
            kw_cache[c.id] = extract_keywords(text, self.stop_words)

        for i in range(len(cells)):
            for j in range(i + 1, len(cells)):
                a, b = cells[i], cells[j]
                if self._same_source(a, b):
                    continue
                overlap = kw_cache[a.id] & kw_cache[b.id]
                if len(overlap) >= self.min_overlap:
                    meta = {"shared_keywords": sorted(overlap), "score": len(overlap)}
                    a.relations.append(Relation(a.id, b.id, "keyword_overlap", meta.copy()))
                    b.relations.append(Relation(b.id, a.id, "keyword_overlap", meta.copy()))

    def _build_code_dependency(self, cells: list[Cell]) -> None:
        code_cells = [c for c in cells if c.content_type == ContentType.CODE]
        name_to_id: dict[str, str] = {}
        for c in code_cells:
            name = c.metadata.get("function") or c.metadata.get("class", "")
            if name:
                name_to_id[name] = c.id
        if not name_to_id:
            return
        for c in code_cells:
            body = c.body if isinstance(c.body, str) else ""
            if not body:
                continue
            for name, target_id in name_to_id.items():
                if c.id != target_id and name in body:
                    c.relations.append(Relation(
                        source_id=c.id, target_id=target_id,
                        relation_type="references",
                        metadata={"referenced_name": name},
                    ))

    def _build_entity_cooccurrence(self, cells: list[Cell]) -> None:
        """Find named entities (capitalized multi-word phrases) co-occurring across docs."""
        import re
        entity_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b')
        entity_cache: dict[str, set[str]] = {}
        for c in cells:
            text = c.body if isinstance(c.body, str) else ""
            entity_cache[c.id] = set(entity_pattern.findall(text))
        for i in range(len(cells)):
            for j in range(i + 1, len(cells)):
                a, b = cells[i], cells[j]
                if self._same_source(a, b):
                    continue
                overlap = entity_cache[a.id] & entity_cache[b.id]
                if overlap:
                    meta = {"shared_entities": sorted(overlap)[:5], "score": len(overlap)}
                    a.relations.append(Relation(a.id, b.id, "entity_cooccurrence", meta.copy()))
                    b.relations.append(Relation(b.id, a.id, "entity_cooccurrence", meta.copy()))

    def _build_citation_links(self, cells: list[Cell]) -> None:
        """Find citation patterns like [1] or (Author, 2023) across cells."""
        import re
        cite_pattern = re.compile(r'\[[\d,\s-]+\]|(?:\([A-Z][a-z]+,\s*\d{4}\))')
        cite_cache: dict[str, set[str]] = {}
        for c in cells:
            text = c.body if isinstance(c.body, str) else ""
            cite_cache[c.id] = set(cite_pattern.findall(text))
        for i in range(len(cells)):
            for j in range(i + 1, len(cells)):
                a, b = cells[i], cells[j]
                if self._same_source(a, b):
                    continue
                overlap = cite_cache[a.id] & cite_cache[b.id]
                if overlap:
                    meta = {"shared_citations": sorted(overlap)[:5], "score": len(overlap)}
                    a.relations.append(Relation(a.id, b.id, "citation", meta.copy()))
                    b.relations.append(Relation(b.id, a.id, "citation", meta.copy()))

    @staticmethod
    def _same_source(a: Cell, b: Cell) -> bool:
        return a.source.resource_path == b.source.resource_path


class HierarchicalAggregator(PipelineTool):
    """Aggregate Cells into a source hierarchy with summary statistics.

    Groups cells by source resource_path, builds a two-level hierarchy
    (source -> cells), and produces per-source metadata cards.
    """

    name = "hierarchical_aggregator"
    input_types: set[ContentType] | None = None
    output_type: ContentType | None = None

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        all_cells: list[Cell] = []
        async for cell in cells:
            all_cells.append(cell)

        if not all_cells:
            return

        # Group cells by source
        groups: dict[str, list[Cell]] = {}
        for cell in all_cells:
            src = cell.source.resource_path if cell.source else "unknown"
            groups.setdefault(src, []).append(cell)

        # Build per-source summary cards
        for src_path, group in groups.items():
            ct_counts: dict[str, int] = {}
            total_chars = 0
            keyword_set: set[str] = set()
            for cell in group:
                ct = cell.content_type.name
                ct_counts[ct] = ct_counts.get(ct, 0) + 1
                if isinstance(cell.body, str):
                    total_chars += len(cell.body)
                    sw = self.stop_words if hasattr(self, 'stop_words') else DEFAULT_STOP_WORDS
                    for kw in extract_keywords(cell.body, sw):
                        keyword_set.add(kw)
                # Yield each original cell
                yield cell

            # Add a summary relation to each cell in the group
            for cell in group:
                cell.metadata["source_stats"] = {
                    "total_cells": len(group),
                    "content_types": ct_counts,
                    "total_chars": total_chars,
                }

    def __init__(self, stop_words: set[str] | None = None):
        self.stop_words = stop_words or DEFAULT_STOP_WORDS
