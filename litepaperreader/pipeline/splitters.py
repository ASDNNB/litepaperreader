from __future__ import annotations

from typing import AsyncIterator

from litepaperreader.core.cell import Cell, ContentType
from litepaperreader.pipeline.tool import PipelineTool, ToolContext


class SemanticSplitter(PipelineTool):
    """Split TEXT Cells on paragraph boundaries with overlap."""

    name = "semantic_splitter"
    input_types = {ContentType.TEXT}
    output_type = ContentType.TEXT

    def __init__(self, max_chars: int = 2000, overlap_chars: int = 200):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            if cell.content_type != ContentType.TEXT:
                yield cell
                continue
            text = cell.body if isinstance(cell.body, str) else ""
            start = 0
            while start < len(text):
                end = self._choose_end(text, start)
                yield Cell(
                    id=f"{cell.id}:seg:{start}",
                    source=cell.source,
                    content_type=ContentType.TEXT,
                    body=text[start:end],
                    structure=cell.structure,
                    relations=cell.relations,
                    metadata=cell.metadata,
                )
                if end >= len(text):
                    break
                start = max(end - self.overlap_chars, start + 1)

    def _choose_end(self, text: str, start: int) -> int:
        hard_end = min(start + self.max_chars, len(text))
        if hard_end == len(text):
            return hard_end
        boundary = text.rfind("\n\n", start + 1, hard_end + 1)
        if boundary > start:
            return boundary + 2
        return hard_end


class CodeSplitter(PipelineTool):
    """Pass-through for CODE Cells (already split by CodeAdapter)."""

    name = "code_splitter"
    input_types = {ContentType.CODE}
    output_type = ContentType.CODE

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            yield cell


class TableSplitter(PipelineTool):
    """Split TABLE Cells into individual row-Cells."""

    name = "table_splitter"
    input_types = {ContentType.TABLE}
    output_type = ContentType.TABLE

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            if cell.content_type != ContentType.TABLE:
                yield cell
                continue
            # If this is a schema/aggregate Cell, split into individual ones
            body = cell.body if isinstance(cell.body, str) else ""
            if "num_rows" in cell.metadata and cell.metadata.get("num_rows", 0) > 1:
                # Already aggregated; pass through
                yield cell
            else:
                yield cell
