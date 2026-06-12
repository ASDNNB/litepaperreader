from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterator

from litepaperreader.connectors.base import ResourceRef, ResourceMeta, SourceConnector


class FileSystemConnector(SourceConnector):
    def __init__(self, include_patterns: list[str] | None = None):
        self._patterns = include_patterns
        self._cached_checksums: dict[str, str] = {}

    def scan(self, path: str) -> Iterator[ResourceRef]:
        p = Path(path)
        if p.is_file():
            yield self._ref_for(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    if self._matches(f):
                        yield self._ref_for(f)

    def read(self, ref: ResourceRef) -> bytes:
        with open(ref.resource_path, "rb") as f:
            return f.read()

    def metadata(self, ref: ResourceRef) -> ResourceMeta:
        st = os.stat(ref.resource_path)
        return ResourceMeta(
            path=ref.resource_path,
            size_bytes=st.st_size,
            content_type=ref.content_type_hint,
        )

    def _ref_for(self, p: Path) -> ResourceRef:
        path_str = str(p.resolve())
        chk = self._checksum(path_str)
        ext = p.suffix.lower()
        return ResourceRef(
            connector="filesystem",
            resource_path=path_str,
            content_type_hint=_ext_to_type(ext),
            size_bytes=p.stat().st_size,
            checksum=chk,
        )

    def _checksum(self, path: str) -> str:
        if path not in self._cached_checksums:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                h.update(f.read(65536))
            self._cached_checksums[path] = h.hexdigest()[:16]
        return self._cached_checksums[path]

    def _matches(self, p: Path) -> bool:
        if not self._patterns:
            return True
        name = p.name.lower()
        return any(name.endswith(pat.lower().lstrip("*")) for pat in self._patterns)


def _ext_to_type(ext: str) -> str:
    mapping = {
        ".pdf": "pdf", ".docx": "docx", ".doc": "doc",
        ".md": "markdown", ".txt": "text",
        ".html": "html", ".htm": "html",
        ".csv": "csv", ".xlsx": "xlsx", ".json": "json",
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".rs": "rust", ".go": "go", ".java": "java",
        ".c": "c", ".cpp": "cpp", ".h": "header",
        ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    }
    return mapping.get(ext, "unknown")
