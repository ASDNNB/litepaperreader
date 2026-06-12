from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from litepaperreader.core.cell import Cell, ContentType, SourceRef, SourceSpan


@dataclass(frozen=True)
class TextChunk:
    """V0.6 compatible chunk, wraps Cell for migration path."""
    text: str
    source_start: int
    source_end: int
    fragments: tuple[SourceSpan, ...]

    def to_cell(self, cell_id: str, source_ref: SourceRef) -> Cell:
        return Cell(
            id=cell_id,
            source=SourceRef(
                connector=source_ref.connector,
                resource_path=source_ref.resource_path,
                resource_checksum=source_ref.resource_checksum,
                span=SourceSpan(self.source_start, self.source_end),
                lineage=(source_ref,),
            ),
            content_type=ContentType.TEXT,
            body=self.text,
            structure=None,
        )


class VirtualPurifier:
    """Immutable source text with dirty-interval skipping."""

    def __init__(self, source_text: str, dirty_intervals: Iterable[tuple[int, int]] = ()):
        self._source_text = source_text
        self._dirty_intervals = self._merge_intervals(dirty_intervals)

    @property
    def source_text(self) -> str:
        return self._source_text

    @property
    def dirty_intervals(self) -> tuple[SourceSpan, ...]:
        return self._dirty_intervals

    def read_safe_chunk(self, start: int, end: int) -> TextChunk:
        self._validate_bounds(start, end, "read range")
        cursor = start
        parts: list[str] = []
        fragments: list[SourceSpan] = []

        for dirty in self._dirty_intervals:
            if dirty.end <= start:
                continue
            if dirty.start >= end:
                break

            clean_end = min(dirty.start, end)
            if cursor < clean_end:
                parts.append(self._source_text[cursor:clean_end])
                fragments.append(SourceSpan(cursor, clean_end))
            cursor = max(cursor, min(dirty.end, end))

        if cursor < end:
            parts.append(self._source_text[cursor:end])
            fragments.append(SourceSpan(cursor, end))

        return TextChunk("".join(parts), start, end, tuple(fragments))

    def _merge_intervals(self, intervals: Iterable[tuple[int, int]]) -> tuple[SourceSpan, ...]:
        spans = []
        for start, end in intervals:
            self._validate_bounds(start, end, "dirty interval")
            if start != end:
                spans.append(SourceSpan(start, end))
        spans.sort()

        merged: list[SourceSpan] = []
        for span in spans:
            if not merged or span.start > merged[-1].end:
                merged.append(span)
            else:
                previous = merged[-1]
                merged[-1] = SourceSpan(previous.start, max(previous.end, span.end))
        return tuple(merged)

    def _validate_bounds(self, start: int, end: int, label: str) -> None:
        if start < 0 or end < start or end > len(self._source_text):
            raise ValueError(
                f"Invalid {label}: ({start}, {end}) for source length {len(self._source_text)}"
            )
