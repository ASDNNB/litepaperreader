from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell


class FormatAdapter(ABC):
    @abstractmethod
    def can_handle(self, ref: ResourceRef) -> bool:
        ...

    @abstractmethod
    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        ...


class AdapterRegistry:
    def __init__(self):
        self._adapters: list[FormatAdapter] = []

    def register(self, adapter: FormatAdapter):
        self._adapters.append(adapter)

    def get_adapter(self, ref: ResourceRef) -> FormatAdapter | None:
        for adapter in self._adapters:
            if adapter.can_handle(ref):
                return adapter
        return None

    def convert(self, ref: ResourceRef, raw: bytes) -> Iterator[Cell]:
        adapter = self.get_adapter(ref)
        if adapter is None:
            raise ValueError(f"No adapter found for: {ref.resource_path} ({ref.content_type_hint})")
        yield from adapter.convert(ref, raw)
