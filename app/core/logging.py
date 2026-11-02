"""Structured logging restricted to non-sensitive fields.

Logs may contain IDs, stage names, statuses, error types, and timings (05-SECURITY-PRIVACY.md §7).
They must never contain filenames, metadata values, OCR text, image contents, or credentials, so
`log_event` drops any field that is not on the allow-list.
"""

import logging
from pathlib import Path

LOGGER_NAME = "vestigo"

ALLOWED_FIELDS = frozenset(
    {"artifact_id", "job_id", "stage", "status", "error_type", "location", "duration_ms", "count"}
)


def configure_logging(level: str) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    safe = {key: value for key, value in fields.items() if key in ALLOWED_FIELDS}
    parts = [f"event={event}", *(f"{key}={value}" for key, value in safe.items() if value is not None)]
    if len(safe) < len(fields):
        parts.append(f"dropped_fields={len(fields) - len(safe)}")
    logger.log(level, " ".join(parts))


def exception_location(exc: BaseException) -> str:
    """Return 'file.py:line' of the innermost frame, without the exception message."""
    tb = exc.__traceback__
    if tb is None:
        return "unknown"
    while tb.tb_next is not None:
        tb = tb.tb_next
    return f"{Path(tb.tb_frame.f_code.co_filename).name}:{tb.tb_lineno}"
