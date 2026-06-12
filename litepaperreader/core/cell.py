from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np


class ContentType(Enum):
    TEXT = auto()
    CODE = auto()
    TABLE = auto()
    IMAGE = auto()
    AUDIO = auto()
    COMPOSITE = auto()


@dataclass(frozen=True, order=True)
class SourceSpan:
    start: int
    end: int


@dataclass(frozen=True)
class SourceRef:
    connector: str
    resource_path: str
    resource_checksum: str
    span: SourceSpan | None = None
    lineage: tuple[SourceRef, ...] = ()


@dataclass
class StructureMeta:
    content_type: ContentType
    hierarchy_level: int = 0
    hierarchy_path: str = ''
    ast: dict[str, Any] | None = None
    schema: dict[str, Any] | None = None
    language: str | None = None


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Cell:
    id: str
    source: SourceRef
    content_type: ContentType
    body: str | bytes
    structure: StructureMeta | None = None
    relations: list[Relation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            'id': self.id,
            'source': {
                'connector': self.source.connector,
                'resource_path': self.source.resource_path,
                'resource_checksum': self.source.resource_checksum,
            },
            'content_type': self.content_type.name,
            'body': self.body if isinstance(self.body, str) else f'<{len(self.body)} bytes>',
            'metadata': self.metadata,
        }
        if self.source.span:
            d['source']['span'] = {'start': self.source.span.start, 'end': self.source.span.end}
        if self.structure:
            d['structure'] = {
                'content_type': self.structure.content_type.name,
                'hierarchy_level': self.structure.hierarchy_level,
                'language': self.structure.language,
            }
        if self.relations:
            d['relations'] = [
                {'source_id': r.source_id, 'target_id': r.target_id, 'type': r.relation_type}
                for r in self.relations
            ]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any], embedding: np.ndarray | None = None) -> Cell:
        src = data['source']
        span_data = src.get('span')
        span = SourceSpan(span_data['start'], span_data['end']) if span_data else None
        source_ref = SourceRef(
            connector=src['connector'],
            resource_path=src['resource_path'],
            resource_checksum=src['resource_checksum'],
            span=span,
        )
        ct = ContentType[data['content_type']]
        struct_data = data.get('structure')
        structure = None
        if struct_data:
            structure = StructureMeta(
                content_type=ContentType[struct_data['content_type']],
                hierarchy_level=struct_data.get('hierarchy_level', 0),
                language=struct_data.get('language'),
            )
        relations = []
        for rd in data.get('relations', []):
            relations.append(Relation(
                source_id=rd['source_id'],
                target_id=rd['target_id'],
                relation_type=rd['type'],
            ))
        return cls(
            id=data['id'],
            source=source_ref,
            content_type=ct,
            body=data['body'],
            structure=structure,
            relations=relations,
            metadata=data.get('metadata', {}),
            embedding=embedding,
        )
