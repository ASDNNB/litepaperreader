"""Test YAML schema directory loading."""
import os
import tempfile

import pytest

from litepaperreader.core.schema import SchemaRegistry

YAML_1 = """template_id: test_tmpl
description: Test template
fields:
  - name: field_a
    description: First field
  - name: field_b
    description: Second field
"""

YAML_2 = """template_id: extra_tmpl
description: Extra template
fields:
  - name: extra_field
    description: Extra field
"""


def test_load_schema_dir():
    pytest.importorskip("yaml")
    reg = SchemaRegistry()
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "test1.yaml"), "w") as f:
            f.write(YAML_1)
        with open(os.path.join(tmp, "test2.yaml"), "w") as f:
            f.write(YAML_2)
        count = reg.load_schema_dir(tmp)
        assert count == 2
        assert "test_tmpl" in reg.list_templates()
        assert "extra_tmpl" in reg.list_templates()
        model = reg.create_model_for("test_tmpl")
        assert "field_a" in model.model_fields
        assert "field_b" in model.model_fields


def test_load_schema_dir_empty():
    reg = SchemaRegistry()
    with tempfile.TemporaryDirectory() as tmp:
        count = reg.load_schema_dir(tmp)
        assert count == 0


def test_load_schema_dir_ignores_non_yaml():
    reg = SchemaRegistry()
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "notes.txt"), "w") as f:
            f.write("not a schema")
        with open(os.path.join(tmp, "data.json"), "w") as f:
            f.write("{}")
        count = reg.load_schema_dir(tmp)
        assert count == 0


def test_load_schema_builtins():
    pytest.importorskip("yaml")
    """Built-in schemas/ directory loads correctly."""
    schema_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "litepaperreader",
        "schemas",
    )
    if os.path.exists(schema_dir):
        reg = SchemaRegistry()
        count = reg.load_schema_dir(schema_dir)
        assert count >= 1
        assert "paper" in reg.list_templates()
