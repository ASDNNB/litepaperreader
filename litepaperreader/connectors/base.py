from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class ResourceRef:
    connector: str
    resource_path: str
    content_type_hint: str = "unknown"
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass
class ResourceMeta:
    path: str
    size_bytes: int | None = None
    content_type: str = "unknown"
    checksum: str | None = None
    extra: dict = None


class SourceConnector(ABC):
    @abstractmethod
    def scan(self, path: str) -> Iterator[ResourceRef]:
        yield

    @abstractmethod
    def read(self, ref: ResourceRef) -> bytes:
        ...

    @abstractmethod
    def metadata(self, ref: ResourceRef) -> ResourceMeta:
        ...
