"""High-level Pipeline orchestrator - source -> connector -> adapter -> toolchain -> knowledge."""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from litepaperreader.adapters.base import AdapterRegistry
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.cell import Cell
from litepaperreader.core.schema import SchemaRegistry
from litepaperreader.knowledge.package import KnowledgePackage, StructuredCard, SummaryNode
from litepaperreader.pipeline.toolchain import Toolchain

logger = logging.getLogger(__name__)


class DataPipeline:
    """Orchestrate the full data processing pipeline.

    Usage::

        pipeline = DataPipeline()
        pipeline.add_default_adapters()
        pipeline.toolchain.add_tool(SemanticSplitter())

        # Process a file
        kp = await pipeline.run_file("document.html")

        # Process raw bytes
        kp = await pipeline.run_raw(ref, raw_bytes)
    """

    def __init__(
        self,
        adapters: AdapterRegistry | None = None,
        toolchain: Toolchain | None = None,
    ):
        self.adapters = adapters or AdapterRegistry()
        self.toolchain = toolchain or Toolchain()

    def add_default_adapters(self):
        """Register all built-in format adapters."""
        from litepaperreader.adapters.html_adapter import HTMLAdapter
        from litepaperreader.adapters.table_adapter import TableAdapter
        from litepaperreader.adapters.code_adapter import CodeAdapter
        self.adapters.register(HTMLAdapter())
        self.adapters.register(TableAdapter())
        self.adapters.register(CodeAdapter())
        try:
            from litepaperreader.adapters.pdf_adapter import PDFAdapter
            self.adapters.register(PDFAdapter())
        except ImportError:
            logger.debug("PDFAdapter not registered (docling not installed)")

    # ------------------------------------------------------------------
    # SchemaExtractor convenience
    # ------------------------------------------------------------------

    def with_schema_extractor(
        self,
        schema_registry: SchemaRegistry,
        template_id: str,
        mode: str = "mock",
        model: str = "gpt-4o-mini",
        api_base: str | None = None,
        api_key: str | None = None,
    ):
        """Add a SchemaExtractor to the pipeline toolchain.

        Returns self for chaining::

            kp = await (DataPipeline()
                .add_default_adapters()
                .with_schema_extractor(reg, "paper", mode="mock")
                .run_raw(ref, html))
        """
        from litepaperreader.pipeline.extractor import SchemaExtractor
        extractor = SchemaExtractor(
            schema_registry=schema_registry,
            template_id=template_id,
            mode=mode,
            model=model,
            api_base=api_base,
            api_key=api_key,
        )
        self.toolchain.add_tool(extractor)
        return self

    # ------------------------------------------------------------------
    # Run methods
    # ------------------------------------------------------------------

    async def run_file(self, path: str) -> KnowledgePackage:
        """Scan a local file/directory and run the full pipeline."""
        from litepaperreader.connectors.filesystem import FileSystemConnector
        connector = FileSystemConnector()
        return await self._run_connector(connector, path)

    async def run_url(self, url: str) -> KnowledgePackage:
        """Fetch a URL and run the full pipeline."""
        from litepaperreader.connectors.web import WebConnector
        connector = WebConnector()
        return await self._run_connector(connector, url)

    async def run_raw(self, ref: ResourceRef, raw: bytes) -> KnowledgePackage:
        """Process raw bytes as if from a connector."""
        logger.info("Processing raw %s (%d bytes)", ref.resource_path, len(raw))
        cells = list(self.adapters.convert(ref, raw))
        processed = await self._run_toolchain(cells)
        return self._build_knowledge(processed)

    async def _run_connector(self, connector, path: str) -> KnowledgePackage:
        refs = list(connector.scan(path))
        if not refs:
            logger.warning("No resources found at %s", path)
            return KnowledgePackage(metadata={"warning": f"No resources at {path}"})

        all_cells: list[Cell] = []
        for ref in refs:
            raw = connector.read(ref)
            cells = list(self.adapters.convert(ref, raw))
            all_cells.extend(cells)
            logger.info("  %s -> %d cells", ref.resource_path, len(cells))

        processed = await self._run_toolchain(all_cells)
        return self._build_knowledge(processed, refs)

    async def _run_toolchain(self, cells: list[Cell]) -> list[Cell]:
        if not self.toolchain.tools:
            return cells

        async def async_iter(items):
            for item in items:
                yield item

        results: list[Cell] = []
        async for cell in self.toolchain.run(async_iter(cells)):
            results.append(cell)
        return results

    # ------------------------------------------------------------------
    # KnowledgePackage construction
    # ------------------------------------------------------------------

    def _build_knowledge(self, cells: list[Cell], refs: list | None = None) -> KnowledgePackage:
        content_types: dict[str, int] = {}
        total_chars = 0
        cards: list[StructuredCard] = []

        for c in cells:
            ct = c.content_type.name
            content_types[ct] = content_types.get(ct, 0) + 1
            if isinstance(c.body, str):
                total_chars += len(c.body)

            # Detect extraction cells by metadata
            if c.metadata.get("type") == "extraction":
                try:
                    fields = json.loads(c.body) if isinstance(c.body, str) else {}
                    card = StructuredCard(
                        schema_id=c.metadata.get("schema", "unknown"),
                        fields=fields,
                        source_cell_id=c.id,
                        source_ref=c.source,
                    )
                    cards.append(card)
                except (json.JSONDecodeError, TypeError):
                    pass

        root = SummaryNode(
            level=0,
            title="Pipeline Results",
            summary=(
                f"{len(cells)} cells from {len(refs) if refs else 1} resource(s), "
                f"{total_chars} total chars, "
                f"{len(cards)} extraction card(s)"
            ),
        )
        return KnowledgePackage(
            cards=cards,
            summary_tree=root,
            metadata={
                "num_cells": len(cells),
                "total_chars": total_chars,
                "content_types": content_types,
                "resources": len(refs) if refs else 1,
                "num_cards": len(cards),
            },
        )

    async def _async_iter(self, items):
        for item in items:
            yield item
