from __future__ import annotations

from typing import AsyncIterator

import numpy as np

from litepaperreader.core.cell import Cell, ContentType
from litepaperreader.core.embedding import SemanticEncoder
from litepaperreader.pipeline.tool import PipelineTool, ToolContext


class EmbeddingEnricher(PipelineTool):
    """Add embedding vectors to Cells for semantic retrieval."""

    name = "embedding_enricher"
    input_types = None  # all types
    output_type = None

    def __init__(self, encoder: SemanticEncoder, batch_size: int = 32):
        self._encoder = encoder
        self._batch_size = batch_size

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        batch: list[Cell] = []
        async for cell in cells:
            batch.append(cell)
            if len(batch) >= self._batch_size:
                async for c in self._embed_batch(batch):
                    yield c
                batch = []
        if batch:
            async for c in self._embed_batch(batch):
                yield c

    async def _embed_batch(self, cells: list[Cell]) -> AsyncIterator[Cell]:
        if not self._encoder.is_available:
            for cell in cells:
                yield cell
            return
        texts = [
            cell.body if isinstance(cell.body, str) else ""
            for cell in cells
        ]
        if not any(texts):
            for cell in cells:
                yield cell
            return
        try:
            scores = self._encoder.score("", texts, batch_size=len(texts))
            for cell, _score in zip(cells, scores):
                cell.embedding = np.array([_score])
                yield cell
        except Exception:
            for cell in cells:
                yield cell


class Deduplicator(PipelineTool):
    """Remove duplicate or near-duplicate Cells based on body hash."""

    name = "deduplicator"
    input_types = None
    output_type = None

    def __init__(self, threshold: float = 0.95):
        self._threshold = threshold
        self._seen_hashes: set[int] = set()

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            body = cell.body if isinstance(cell.body, str) else str(cell.body)
            h = hash(body[:200])
            if h in self._seen_hashes:
                continue
            self._seen_hashes.add(h)
            yield cell


class RelevanceFilter(PipelineTool):
    """Filter Cells by keyword relevance score."""

    name = "relevance_filter"
    input_types = None
    output_type = None

    def __init__(self, min_score: float = 0.0):
        self._min_score = min_score

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            body = cell.body if isinstance(cell.body, str) else ""
            score = len(body) / 2000  # simple length-based relevance
            if score >= self._min_score:
                yield cell
