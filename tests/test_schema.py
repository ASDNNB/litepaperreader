"""Migrated from V0.6: SchemaRegistry tests."""
import pytest
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec


def test_creates_flat_pydantic_model_with_nullable_string_fields():
    registry = SchemaRegistry()
    registry.register(
        SchemaTemplate(
            template_id="paper",
            description="Academic paper",
            fields=(
                FieldSpec(name="claim", description="Main claim"),
                FieldSpec(name="method", description="Method summary"),
            ),
        )
    )
    model = registry.create_model_for("paper")
    instance = model.model_validate({"claim": "Fast retrieval"})
    assert instance.claim == "Fast retrieval"
    assert instance.method is None
    assert model.model_fields["claim"].description == "Main claim"


@pytest.mark.parametrize(
    "field",
    [
        FieldSpec(name="", description="empty"),
        FieldSpec(name="bad.name", description="nested-like"),
        FieldSpec(name="items[0]", description="array-like"),
    ],
)
def test_rejects_invalid_field_names(field):
    registry = SchemaRegistry()
    with pytest.raises(ValueError):
        registry.register(SchemaTemplate(template_id="bad", description="Bad", fields=(field,)))


def test_rejects_duplicate_fields():
    registry = SchemaRegistry()
    with pytest.raises(ValueError):
        registry.register(
            SchemaTemplate(
                template_id="dup", description="Duplicate",
                fields=(
                    FieldSpec(name="claim", description="First"),
                    FieldSpec(name="claim", description="Second"),
                ),
            )
        )


def test_list_templates():
    registry = SchemaRegistry()
    registry.register(SchemaTemplate(template_id="a", description="A", fields=()))
    registry.register(SchemaTemplate(template_id="b", description="B", fields=()))
    assert set(registry.list_templates()) == {"a", "b"}
