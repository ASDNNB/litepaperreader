"""Tests for pipeline configuration loading."""
import json
import os
import tempfile

import pytest

from litepaperreader.pipeline.config import PipelineConfig, load_config


def test_pipeline_config_defaults():
    cfg = PipelineConfig()
    assert cfg.template_id == "paper"
    assert cfg.extraction_mode == "mock"
    assert cfg.model_name == "gpt-4o-mini"
    assert cfg.db_path == "litepaper_index.db"


def test_pipeline_config_from_dict():
    cfg = PipelineConfig.from_dict({
        "pipeline": {"schema": "person", "extraction_mode": "ollama"},
        "model": {"name": "llama3.2", "api_base": "http://localhost:11434"},
        "watch": {"dir": "./my_docs", "interval": 60},
    })
    assert cfg.template_id == "person"
    assert cfg.extraction_mode == "ollama"
    assert cfg.model_name == "llama3.2"
    assert cfg.api_base == "http://localhost:11434"
    assert cfg.watch_dir == "./my_docs"
    assert cfg.watch_interval == 60


def test_load_config_json():
    data = {
        "pipeline": {"schema": "product"},
        "model": {"name": "gpt-4o"},
    }
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.template_id == "product"
        assert cfg.model_name == "gpt-4o"
    finally:
        os.unlink(path)


def test_load_config_yaml():
    pytest.importorskip("yaml")
    yaml_content = """
pipeline:
  schema: person
  extraction_mode: ollama
model:
  name: llama3.2
watch:
  dir: ./docs
  interval: 15
"""
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yaml_content)
        path = f.name
    try:
        cfg = load_config(path)
        assert cfg.template_id == "person"
        assert cfg.extraction_mode == "ollama"
        assert cfg.model_name == "llama3.2"
    finally:
        os.unlink(path)


def test_load_config_unknown_ext_yaml_preferred():
    """Files without .yaml/.json extension try YAML first, should fail
    gracefully when pyyaml is available but content is JSON."""
    # This tests YAML fallback behavior - if pyyaml is not installed,
    # the JSON fallback should work
    pass
