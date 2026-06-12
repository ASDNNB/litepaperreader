from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from litepaperreader.core.cell import Cell, SourceRef


@dataclass
class StructuredCard:
    schema_id: str
    fields: dict[str, Any]
    source_cell_id: str
    source_ref: SourceRef | None = None
    confidence: float = 1.0


@dataclass
class ProvenanceMap:
    card_to_cell: dict[str, str] = field(default_factory=dict)
    cell_to_resource: dict[str, SourceRef] = field(default_factory=dict)


@dataclass
class SummaryNode:
    level: int
    title: str
    summary: str
    children: list[SummaryNode] = field(default_factory=list)
    cell_ids: list[str] = field(default_factory=list)


@dataclass
class KnowledgePackage:
    cards: list[StructuredCard] = field(default_factory=list)
    summary_tree: SummaryNode | None = None
    provenance: ProvenanceMap = field(default_factory=ProvenanceMap)
    metadata: dict[str, Any] = field(default_factory=dict)
