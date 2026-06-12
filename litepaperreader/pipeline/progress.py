"""Progress tracking for pipeline execution."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class Stage(Enum):
    ADAPTER = "adapter"
    SPLITTER = "splitter"
    EXTRACTOR = "extractor"
    RELATION = "relation"
    ANSWER = "answer"
    WATCHER = "watcher"
    PIPELINE = "pipeline"


@dataclass
class ProgressEvent:
    stage: Stage
    status: str
    message: str = ""
    current: int = 0
    total: int = 0
    elapsed: float = 0.0


ProgressCallback = Callable[[ProgressEvent], None]


class ProgressTracker:
    """Report pipeline execution progress via callbacks and logs.

    Usage::

        tracker = ProgressTracker()
        tracker.on(Stage.ADAPTER, "start", "Converting...")
        tracker.on(Stage.ADAPTER, "complete", "3 cells")
    """

    def __init__(self, callback: ProgressCallback | None = None):
        self.callback = callback
        self._times: dict[str, float] = {}

    def on(
        self,
        stage: str | Stage,
        status: str,
        message: str = "",
        current: int = 0,
        total: int = 0,
    ) -> None:
        if isinstance(stage, str):
            try:
                stage = Stage(stage)
            except ValueError:
                stage = Stage.PIPELINE

        elapsed = 0.0
        key = stage.value
        if status == "start":
            self._times[key] = time.monotonic()
        elif status in ("complete", "error"):
            t0 = self._times.pop(key, None)
            if t0:
                elapsed = time.monotonic() - t0

        ev = ProgressEvent(stage, status, message, current, total, elapsed)
        if self.callback:
            self.callback(ev)
        if elapsed > 0:
            logger.info("[%s] %s (%.2fs) %s", stage.value, status, elapsed, message)
        else:
            logger.info("[%s] %s %s", stage.value, status, message)


def default_tracker() -> ProgressTracker:
    return ProgressTracker()
