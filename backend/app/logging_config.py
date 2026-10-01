"""Structured JSON logging.

One JSON object per line so logs can be shipped/queried (e.g. Loki, CloudWatch Logs
Insights). The HTTP middleware in app.main adds one line per request with method, path,
status, duration and the authenticated user id.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.config import get_settings

_REQUEST_KEYS = ("request_id", "user_id", "method", "path", "status", "duration_ms")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key in _REQUEST_KEYS:  # extras attached by the request middleware
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(get_settings().log_level.upper())
    # We emit our own request line from middleware; drop uvicorn's default access log.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
