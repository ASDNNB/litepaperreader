"""Tests for ProgressTracker."""
from litepaperreader.pipeline.progress import ProgressTracker, Stage, ProgressEvent


def test_tracker_start_complete():
    events = []
    t = ProgressTracker(callback=lambda e: events.append(e))
    t.on(Stage.ADAPTER, "start", "converting")
    t.on(Stage.ADAPTER, "complete", "3 cells")
    assert len(events) == 2
    assert events[0].status == "start"
    assert events[1].status == "complete"
    assert events[1].stage == Stage.ADAPTER


def test_tracker_string_stage():
    events = []
    t = ProgressTracker(callback=lambda e: events.append(e))
    t.on("splitter", "start")
    t.on("splitter", "complete")
    assert len(events) == 2
    assert events[0].stage == Stage.SPLITTER


def test_tracker_invalid_stage_fallsback():
    events = []
    t = ProgressTracker(callback=lambda e: events.append(e))
    t.on("nonexistent", "start")
    assert events[0].stage == Stage.PIPELINE


def test_tracker_elapsed_time():
    events = []
    t = ProgressTracker(callback=lambda e: events.append(e))
    t.on(Stage.ADAPTER, "start")
    import time; time.sleep(0.05)
    t.on(Stage.ADAPTER, "complete")
    assert events[1].elapsed >= 0


def test_tracker_no_callback():
    t = ProgressTracker()
    t.on(Stage.PIPELINE, "start", "works without callback")
    t.on(Stage.PIPELINE, "complete", "still works")
