"""Migrated from V0.6: ingestion tests + Cell integration."""
import pytest
from litepaperreader.core.cell import Cell, ContentType, SourceRef, SourceSpan, Relation, StructureMeta
from litepaperreader.core.purifier import VirtualPurifier


# === V0.6 legacy tests (ingestion) ===

def test_merges_unordered_overlapping_and_adjacent_dirty_intervals():
    purifier = VirtualPurifier(
        "abcdefghijklmnopqrstuvwxyz",
        dirty_intervals=[(10, 12), (2, 5), (4, 8), (8, 9)],
    )
    assert purifier.dirty_intervals == (SourceSpan(2, 9), SourceSpan(10, 12))


def test_read_safe_chunk_skips_dirty_text_and_preserves_fragments():
    purifier = VirtualPurifier("AA dirty BB noise CC", dirty_intervals=[(3, 9), (12, 18)])
    chunk = purifier.read_safe_chunk(0, len("AA dirty BB noise CC"))
    assert chunk.text == "AA BB CC"
    assert chunk.source_start == 0
    assert chunk.source_end == 20
    assert chunk.fragments == (SourceSpan(0, 3), SourceSpan(9, 12), SourceSpan(18, 20))


@pytest.mark.parametrize("interval", [(-1, 2), (3, 2), (0, 99)])
def test_rejects_invalid_dirty_intervals(interval):
    with pytest.raises(ValueError):
        VirtualPurifier("abc", dirty_intervals=[interval])


@pytest.mark.parametrize("start,end", [(-1, 2), (2, 1), (0, 4)])
def test_rejects_invalid_read_ranges(start, end):
    purifier = VirtualPurifier("abc")
    with pytest.raises(ValueError):
        purifier.read_safe_chunk(start, end)


# === New V1.0 Cell tests ===

def test_cell_creation():
    ref = SourceRef(connector="test", resource_path="/f.txt", resource_checksum="abc")
    cell = Cell(id="c1", source=ref, content_type=ContentType.TEXT, body="hello")
    assert cell.id == "c1"
    assert cell.content_type == ContentType.TEXT
    assert cell.source.connector == "test"


def test_cell_to_dict_roundtrip():
    ref = SourceRef(
        connector="fs", resource_path="/doc.md", resource_checksum="xyz",
        span=SourceSpan(10, 20),
    )
    rel = Relation(source_id="c1", target_id="c2", relation_type="references")
    struct = StructureMeta(content_type=ContentType.TEXT, language="en")
    cell = Cell(
        id="c1", source=ref, content_type=ContentType.TEXT, body="text body",
        structure=struct, relations=[rel], metadata={"key": "val"},
    )
    d = cell.to_dict()
    assert d["id"] == "c1"
    assert d["content_type"] == "TEXT"
    assert d["source"]["span"]["start"] == 10
    assert len(d["relations"]) == 1
    c2 = Cell.from_dict(d)
    assert c2.id == cell.id
    assert c2.content_type == cell.content_type
    assert c2.source.span.start == 10


def test_cell_content_type_enum():
    assert ContentType.TEXT.value == 1
    assert ContentType.CODE.value == 2
    assert ContentType.TABLE.value == 3
    assert ContentType.COMPOSITE.value == 6


def test_source_ref_with_lineage():
    parent = SourceRef(connector="git", resource_path="/repo/main.py", resource_checksum="p1")
    child = SourceRef(
        connector="git", resource_path="/repo/main.py", resource_checksum="p1",
        span=SourceSpan(10, 20), lineage=(parent,),
    )
    assert child.lineage[0].resource_path == parent.resource_path
