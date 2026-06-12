from __future__ import annotations

import hashlib
from typing import Iterator

from litepaperreader.adapters.base import FormatAdapter
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell, ContentType, SourceRef, SourceSpan, StructureMeta

LANGUAGE_MAP = {
    "py": "python", "js": "javascript", "ts": "typescript",
    "rs": "rust", "go": "go", "java": "java",
    "c": "c", "cpp": "cpp", "h": "c",
    "rb": "ruby", "php": "php", "swift": "swift",
    "kt": "kotlin", "scala": "scala", "r": "r",
}


class CodeAdapter(FormatAdapter):
    """Convert source code files to CODE Cell stream with AST-aware splitting."""

    def can_handle(self, ref: ResourceRef) -> bool:
        ext = ref.resource_path.rsplit(".", 1)[-1].lower()
        return ext in LANGUAGE_MAP

    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        ext = ref.resource_path.rsplit(".", 1)[-1].lower()
        lang = LANGUAGE_MAP.get(ext, "unknown")
        checksum = hashlib.sha256(raw).hexdigest()[:16]
        source_ref = SourceRef(
            connector=ref.connector,
            resource_path=ref.resource_path,
            resource_checksum=checksum,
        )
        text = raw.decode("utf-8", errors="replace")

        # Try tree-sitter first
        parsed = self._parse_with_treesitter(text, lang)
        if parsed:
            for fn_name, fn_body, fn_start, fn_end in parsed:
                yield Cell(
                    id=f"{ref.connector}:{checksum}:func:{fn_name}",
                    source=SourceRef(
                        connector=ref.connector,
                        resource_path=ref.resource_path,
                        resource_checksum=checksum,
                        span=SourceSpan(fn_start, fn_end),
                    ),
                    content_type=ContentType.CODE,
                    body=fn_body,
                    structure=StructureMeta(
                        content_type=ContentType.CODE,
                        language=lang,
                        ast={"type": "function", "name": fn_name},
                    ),
                    metadata={"function": fn_name, "lines": f"{fn_start}-{fn_end}"},
                )
        else:
            # Fallback: one Cell per file
            yield Cell(
                id=f"{ref.connector}:{checksum}:file",
                source=source_ref,
                content_type=ContentType.CODE,
                body=text,
                structure=StructureMeta(
                    content_type=ContentType.CODE,
                    language=lang,
                    hierarchy_level=0,
                ),
                metadata={"lines": len(text.splitlines()), "language": lang},
            )

    def _parse_with_treesitter(self, text: str, lang: str) -> list[tuple[str, str, int, int]] | None:
        try:
            from tree_sitter_languages import get_parser
            parser = get_parser(lang)
        except Exception:
            return None

        tree = parser.parse(text.encode("utf-8"))
        results = []

        def walk(node, depth=0):
            if node.type in (
                "function_definition", "function_declaration",
                "method_definition", "class_declaration",
                "class_definition",
            ):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = text[name_node.start_byte:name_node.end_byte]
                    body = text[node.start_byte:node.end_byte]
                    results.append((name, body, node.start_point[0], node.end_point[0]))
                if depth > 5:
                    return
            for child in node.children:
                walk(child, depth + 1)

        walk(tree.root_node)
        return results if results else None
