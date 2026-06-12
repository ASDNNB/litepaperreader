from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterator

from litepaperreader.connectors.base import ResourceRef, ResourceMeta, SourceConnector
from litepaperreader.connectors.filesystem import _ext_to_type


class GitConnector(SourceConnector):
    def __init__(self, repo_path: str | None = None):
        self._repo_path = repo_path

    def scan(self, path: str) -> Iterator[ResourceRef]:
        repo = self._find_repo(path)
        if not repo:
            return
        result = subprocess.run(
            ["git", "-C", repo, "ls-files"],
            capture_output=True, text=True, check=True,
        )
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            full = os.path.join(repo, line)
            if os.path.isfile(full):
                ext = Path(line).suffix.lower()
                st = os.stat(full)
                yield ResourceRef(
                    connector="git",
                    resource_path=full,
                    content_type_hint=_ext_to_type(ext),
                    size_bytes=st.st_size,
                )

    def read(self, ref: ResourceRef) -> bytes:
        with open(ref.resource_path, "rb") as f:
            return f.read()

    def metadata(self, ref: ResourceRef) -> ResourceMeta:
        st = os.stat(ref.resource_path)
        return ResourceMeta(path=ref.resource_path, size_bytes=st.st_size)

    def _find_repo(self, path: str) -> str | None:
        p = Path(path).resolve()
        if self._repo_path:
            return self._repo_path
        for parent in [p] + list(p.parents):
            if (parent / ".git").is_dir():
                return str(parent)
        return None
