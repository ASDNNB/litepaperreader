"""Tests for PipelineDB persistence."""
import os
import tempfile
import time

import pytest

from litepaperreader.pipeline.watcher import PipelineDB, checksum, SUPPORTED_EXTENSIONS


def test_pipeline_db_create():
    """PipelineDB creates tables on init."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PipelineDB(db_path)
        # Verify tables exist by querying
        rows = db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = [r[0] for r in rows]
        assert "files" in names
        assert "cells" in names
        assert "cards" in names
        db.close()
    finally:
        os.unlink(db_path)


def test_is_unchanged():
    """is_unchanged returns True for matching checksum, False otherwise."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PipelineDB(db_path)
        path = "/test/file.txt"

        # No record yet
        assert db.is_unchanged(path, "abc123") is False

        # Save and check
        db.save_file(path, "abc123", 100, "sess_1")
        assert db.is_unchanged(path, "abc123") is True
        assert db.is_unchanged(path, "xyz789") is False

        db.close()
    finally:
        os.unlink(db_path)


def test_checksum():
    """checksum produces consistent results."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        path = f.name
    try:
        c1 = checksum(path)
        c2 = checksum(path)
        assert c1 == c2
        assert len(c1) == 16  # sha256[:16]
    finally:
        os.unlink(path)


def test_search_cards():
    """search_cards returns matching results."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PipelineDB(db_path)

        # Insert a card directly
        db._conn.execute(
            "INSERT INTO cards (id, cell_id, session_id, schema_id, fields, confidence) VALUES (?, ?, ?, ?, ?, ?)",
            ("card1", "cell1", "sess_1", "paper", '{"method": "deep learning", "finding": "good"}', 1.0),
        )
        db._conn.commit()

        results = db.search_cards("deep")
        assert len(results) >= 1
        assert results[0]["schema_id"] == "paper"

        results2 = db.search_cards("nonexistent")
        assert len(results2) == 0

        db.close()
    finally:
        os.unlink(db_path)


def test_get_all_sessions():
    """get_all_sessions returns distinct session IDs."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PipelineDB(db_path)
        db.save_file("/a.txt", "a1", 10, "sess_a")
        db.save_file("/b.txt", "b1", 20, "sess_b")

        sessions = db.get_all_sessions()
        assert "sess_a" in sessions
        assert "sess_b" in sessions

        db.close()
    finally:
        os.unlink(db_path)


def test_supported_extensions():
    assert ".html" in SUPPORTED_EXTENSIONS
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".py" in SUPPORTED_EXTENSIONS
    assert ".csv" in SUPPORTED_EXTENSIONS
