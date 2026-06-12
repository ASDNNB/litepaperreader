"""LitePaperReader error types and user-friendly formatting."""
from __future__ import annotations

import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)


class LitePaperError(Exception):
    """Base exception. Subclasses set ``code`` and ``hint``."""

    code: str = "UNKNOWN_ERROR"
    hint: str = "An unexpected error occurred. \n\u53d1\u751f\u610f\u5916\u9519\u8bef\uff0c\u8bf7\u67e5\u770b\u65e5\u5fd7."

    def __init__(
        self,
        message: str = "",
        hint: str = "",
        original: Exception | None = None,
    ):
        super().__init__(message or self.__class__.__name__)
        self.original = original
        if hint:
            self.hint = hint

    def log(self) -> None:
        logger.error("[%s] %s", self.code, self.hint)
        if self.original:
            logger.debug(
                "Caused by:\n%s",
                "".join(
                    traceback.format_exception(
                        type(self.original),
                        self.original,
                        self.original.__traceback__,
                    )
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.code,
            "message": self.hint,
            "detail": self.args[0] if self.args else "",
        }


class ConfigError(LitePaperError):
    code = "CONFIG_ERROR"
    hint = "Invalid configuration. \u914d\u7f6e\u65e0\u6548\uff0c\u8bf7\u68c0\u67e5\u914d\u7f6e\u6587\u4ef6\u3002"


class ConnectorError(LitePaperError):
    code = "CONNECTOR_ERROR"
    hint = "Failed to read data from the source. \u65e0\u6cd5\u8bfb\u53d6\u6570\u636e\u6e90\uff0c\u8bf7\u68c0\u67e5\u8def\u5f84\u6216\u7f51\u7edc\u8fde\u63a5\u3002"


class AdapterError(LitePaperError):
    code = "ADAPTER_ERROR"
    hint = "Failed to convert the input data. \u65e0\u6cd5\u8f6c\u6362\u8f93\u5165\u6570\u636e\uff0c\u683c\u5f0f\u53ef\u80fd\u4e0d\u53d7\u652f\u6301\u3002"


class PipelineError(LitePaperError):
    code = "PIPELINE_ERROR"
    hint = "The pipeline encountered an error. \u7ba1\u9053\u5904\u7406\u65f6\u53d1\u751f\u9519\u8bef\uff0c\u8bf7\u67e5\u770b\u65e5\u5fd7\u3002"


class ExtractionError(LitePaperError):
    code = "EXTRACTION_ERROR"
    hint = "Failed to extract structured information. \u65e0\u6cd5\u4ece\u6587\u672c\u4e2d\u63d0\u53d6\u7ed3\u6784\u5316\u4fe1\u606f\u3002"


class AnswerError(LitePaperError):
    code = "ANSWER_ERROR"
    hint = "Failed to generate an answer. \u65e0\u6cd5\u57fa\u4e8e\u63d0\u53d6\u6570\u636e\u751f\u6210\u56de\u7b54\u3002"


class ValidationError(LitePaperError):
    code = "VALIDATION_ERROR"
    hint = "The input data is invalid. \u8f93\u5165\u6570\u636e\u65e0\u6548\u6216\u683c\u5f0f\u9519\u8bef\u3002"


def wrap(err: Exception) -> LitePaperError:
    """Convert a raw exception to the closest ``LitePaperError`` type."""
    if isinstance(err, LitePaperError):
        return err
    for exc_type in (ConfigError, ConnectorError, AdapterError,
                     PipelineError, ExtractionError, AnswerError, ValidationError):
        if type(err).__name__ in dir(exc_type) or any(
            k in str(err).lower() for k in ("config", "yaml", "json")
        ):
            return exc_type(str(err), original=err)
    return LitePaperError(str(err), original=err)


def safe(callback, *args, **kwargs):
    """Execute *callback*, wrapping any exception in a ``LitePaperError``.

    Returns ``(result, None)`` on success or ``(None, error_dict)`` on failure.
    """
    try:
        return callback(*args, **kwargs), None
    except LitePaperError:
        raise
    except Exception as exc:
        wrapped = wrap(exc)
        wrapped.log()
        return None, wrapped.to_dict()
