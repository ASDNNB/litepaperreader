from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from litepaperreader.core.cell import Cell, ContentType


@dataclass
class ToolContext:
    config: dict = field(default_factory=dict)
    logger: Callable[[str], None] = lambda msg: None
    checkpoint: dict[str, set[str]] = field(default_factory=lambda: {"completed": set(), "failed": {}})


class PipelineTool(ABC):
    name: str = "base_tool"
    input_types: set[ContentType] | None = None
    output_type: ContentType | None = None

    @abstractmethod
    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        ...

        if False:
            yield  # pragma: no cover
