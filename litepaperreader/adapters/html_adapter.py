from __future__ import annotations

import hashlib
from typing import Iterator

from litepaperreader.adapters.base import FormatAdapter
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell, ContentType, SourceRef, StructureMeta


class HTMLAdapter(FormatAdapter):
    """Convert HTML content to TEXT Cell stream using trafilatura."""

    def can_handle(self, ref: ResourceRef) -> bool:
        hint = ref.content_type_hint.lower()
        if hint == "html":
            return True
        ext = ref.resource_path.rsplit(".", 1)[-1].lower()
        return ext in ("html", "htm")

    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        checksum = hashlib.sha256(raw).hexdigest()[:16]
        source_ref = SourceRef(
            connector=ref.connector,
            resource_path=ref.resource_path,
            resource_checksum=checksum,
        )
        text = self._extract_text(raw)
        if not text.strip():
            yield Cell(
                id=f"{ref.connector}:{checksum}:empty",
                source=source_ref,
                content_type=ContentType.TEXT,
                body="",
                metadata={"warning": "No extractable text found"},
            )
            return

        sections = text.split("\n\n")
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
                ),
                content_type=ContentType.TEXT,
                body=sec,
                structure=StructureMeta(content_type=ContentType.TEXT, hierarchy_level=0),
            )

    def _extract_text(self, raw: bytes) -> str:
        try:
            import trafilatura
            text = trafilatura.extract(raw)
            if text:
                return text
        except ImportError:
            pass
        try:
            from readability import Document
            import re
            doc = Document(raw)
            html = doc.summary()
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except ImportError:
            pass
        return raw.decode("utf-8", errors="replace")
