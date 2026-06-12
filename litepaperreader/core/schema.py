from __future__ import annotations

from dataclasses import dataclass
from re import fullmatch

from pydantic import Field, create_model


@dataclass(frozen=True)
class FieldSpec:
    name: str
    description: str


@dataclass(frozen=True)
class SchemaTemplate:
    template_id: str
    description: str
    fields: tuple[FieldSpec, ...]


class SchemaRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, SchemaTemplate] = {}

    def register(self, template: SchemaTemplate) -> None:
        self._validate_template(template)
        self._templates[template.template_id] = template

    def register_from_yaml(self, yaml_path: str) -> SchemaTemplate:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fields = tuple(
            FieldSpec(name=f["name"], description=f["description"])
            for f in data["fields"]
        )
        template = SchemaTemplate(
            template_id=data["template_id"],
            description=data["description"],
            fields=fields,
        )
        self.register(template)
        return template

    def create_model_for(self, template_id: str):
        try:
            template = self._templates[template_id]
        except KeyError as exc:
            raise KeyError(f"Unknown schema template: {template_id}") from exc
        fields = {
            spec.name: (str | None, Field(default=None, description=spec.description))
            for spec in template.fields
        }
        model_name = f"{template.template_id.title().replace('_', '')}Extraction"
        return create_model(model_name, **fields)

    def load_schema_dir(self, dir_path: str) -> int:
        """Load all YAML schema files from a directory."""
        import os
        count = 0
        for f in sorted(os.listdir(dir_path)):
            if f.endswith((".yaml", ".yml")):
                try:
                    self.register_from_yaml(os.path.join(dir_path, f))
                    count += 1
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to load schema %s: %s", f, e)
        return count

    def list_templates(self) -> list[str]:
        return list(self._templates.keys())

    def _validate_template(self, template: SchemaTemplate) -> None:
        if not template.template_id.strip():
            raise ValueError("Schema template_id cannot be empty")
        seen: set[str] = set()
        for field in template.fields:
            if not fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field.name):
                raise ValueError(f"Invalid flat field name: {field.name!r}")
            if field.name in seen:
                raise ValueError(f"Duplicate field name: {field.name}")
            seen.add(field.name)
