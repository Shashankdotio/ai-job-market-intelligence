"""Structured logging helpers for command-line pipeline runs."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


_CONTEXT_FIELDS = (
    "event",
    "provider",
    "company",
    "job_id",
    "output_path",
    "job_count",
    "failed_company_count",
    "detail_failure_count",
)


class JsonFormatter(logging.Formatter):
    """Render pipeline logs as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(verbose: bool = False) -> None:
    """Configure application logging once for a CLI invocation."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
