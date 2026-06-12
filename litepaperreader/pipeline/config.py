"""Pipeline configuration loading from YAML/JSON.

Usage::

    from litepaperreader.pipeline.config import load_config, configure_pipeline
    from litepaperreader.core.schema import SchemaRegistry

    cfg = load_config("litepaper_config.yaml")
    pipeline = configure_pipeline(cfg, registry)
    # pipeline is ready to use
"""
from __future__ import annotations
import pathlib

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.pipeline.splitters import SemanticSplitter
from litepaperreader.pipeline.aggregators import RelationBuilder

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """All configuration for a LitePaperReader pipeline.

    Create via ``load_config()`` from a YAML or JSON file.

    Example YAML (``litepaper_config.yaml``)::

        pipeline:
          schema: paper
          extraction_mode: mock
        model:
          mode: ollama
          name: llama3.2
          api_base: http://localhost:11434
        watch:
          dir: ./docs
          interval: 30
          db: index.db
    """

    # Schema & extraction
    template_id: str = "paper"
    schema_dir: str | None = None
    extraction_mode: str = "mock"

    # Model (used when extraction_mode != "mock")
    model_name: str = "gpt-4o-mini"
    api_base: str | None = None
    api_key: str | None = None

    # Pipeline tools
    splitter_max_chars: int = 1000
    splitter_overlap: int = 100
    relation_strategy: str = "keyword_overlap"
    relation_min_overlap: int = 2

    # Watch mode
    watch_dir: str | None = None
    watch_interval: int = 30
    db_path: str | None = "litepaper_index.db"

    # Logging
    log_level: str = "INFO"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineConfig:
        p = data.get("pipeline", {})
        m = data.get("model", {})
        w = data.get("watch", {})
        l = data.get("logging", {})
        return cls(
            template_id=p.get("schema", "paper"),
            schema_dir=p.get("schema_dir"),
            extraction_mode=p.get("extraction_mode", "mock"),
            model_name=m.get("name", "gpt-4o-mini"),
            api_base=m.get("api_base"),
            api_key=m.get("api_key"),
            splitter_max_chars=p.get("splitter_max_chars", 1000),
            splitter_overlap=p.get("splitter_overlap", 100),
            relation_strategy=p.get("relation_strategy", "keyword_overlap"),
            relation_min_overlap=p.get("relation_min_overlap", 2),
            watch_dir=w.get("dir"),
            watch_interval=w.get("interval", 30),
            db_path=w.get("db", "litepaper_index.db"),
            log_level=l.get("level", "INFO"),
        )


def load_config(path: str | Path) -> PipelineConfig:
    """Load ``PipelineConfig`` from a YAML or JSON file.

    Args:
        path: Path to ``.yaml``, ``.yml``, or ``.json`` file.

    Returns:
        Populated ``PipelineConfig`` instance.
    """
    path = Path(path)
    data: dict[str, Any]

    if path.suffix in (".yaml", ".yml"):
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    elif path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except ImportError:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
    return PipelineConfig.from_dict(data)


def configure_pipeline(
    config: PipelineConfig,
    registry=None,
) -> DataPipeline:
    """Create a fully configured ``DataPipeline`` from a ``PipelineConfig``.

    Args:
        config: The pipeline configuration.
        registry: Optional ``SchemaRegistry`` with registered templates.
                 Uses built-in defaults if omitted.

    Returns:
        A ready-to-use ``DataPipeline``.
    """
    pipeline = DataPipeline()
    pipeline.add_default_adapters()
    pipeline.toolchain.add_tool(
        SemanticSplitter(
            max_chars=config.splitter_max_chars,
            overlap_chars=config.splitter_overlap,
        )
    )
    pipeline.toolchain.add_tool(
        RelationBuilder(
            strategy=config.relation_strategy,
            min_overlap=config.relation_min_overlap,
        )
    )
    if config.schema_dir:
        sd = pathlib.Path(config.schema_dir)
        if sd.exists():
            registry.load_schema_dir(str(sd)) if registry else None
    if registry:
        pipeline.with_schema_extractor(
            registry,
            template_id=config.template_id,
            mode=config.extraction_mode,
            model=config.model_name,
            api_base=config.api_base,
            api_key=config.api_key,
        )
    return pipeline


def setup_logging(config: PipelineConfig) -> None:
    """Configure the root logger from a ``PipelineConfig``."""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
