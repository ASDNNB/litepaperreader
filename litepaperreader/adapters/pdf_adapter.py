from __future__ import annotations

import hashlib
from typing import Iterator

from litepaperreader.adapters.base import FormatAdapter
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell, ContentType, SourceRef, SourceSpan, StructureMeta


class PDFAdapter(FormatAdapter):
    def can_handle(self, ref: ResourceRef) -> bool:
        ext = ref.resource_path.rsplit(".", 1)[-1].lower()
        return ext in ("pdf",)

    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        checksum = hashlib.sha256(raw).hexdigest()[:16]
        try:
            yield from self._convert_with_docling(ref, raw, checksum)
        except ImportError:
            yield from self._fallback_text(ref, checksum)

    def _convert_with_docling(self, ref: ResourceRef, raw: bytes, checksum: str) -> Iterator[Cell]:
        from docling.document_converter import DocumentConverter
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            md_text = result.document.export_to_markdown()
        finally:
            os.unlink(tmp_path)

        source_ref = SourceRef(
            connector=ref.connector,
            resource_path=ref.resource_path,
            resource_checksum=checksum,
        )

        sections = md_text.split("\n\n")
        for i, sec in enumerate(sections):
            sec = sec.strip()
            if not sec:
                continue
            yield Cell(
                id=f"{ref.connector}:{checksum}:text:{i:04d}",
                source=SourceRef(
                    connector=ref.connector,
                    resource_path=ref.resource_path,
                    resource_checksum=checksum,
                    span=SourceSpan(0, 0),
                ),
                content_type=ContentType.TEXT,
                body=sec,
                structure=StructureMeta(
                    content_type=ContentType.TEXT,
                    hierarchy_level=0,
                ),
            )

    def _fallback_text(self, ref: ResourceRef, checksum: str) -> Iterator[Cell]:
        import tempfile, os, subprocess
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            pass
        # Best-effort: return a single cell noting no converter available
        yield Cell(
            id=f"{ref.connector}:{checksum}:fallback",
            source=SourceRef(
                connector=ref.connector,
                resource_path=ref.resource_path,
                resource_checksum=checksum,
            ),
            content_type=ContentType.TEXT,
            body=f"[PDFAdapter] No docling available for: {ref.resource_path}",
            structure=StructureMeta(content_type=ContentType.TEXT),
        )
