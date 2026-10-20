"""Structured JSON logging helpers shared by both Lambdas."""
import json
import logging
import os
import time
import uuid
from contextvars import ContextVar

# Correlation id carried through a single invocation / job.
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for easy CloudWatch querying."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": _correlation_id.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Attach any structured 'extra' fields.
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(LOG_LEVEL)
    return logger


def log(logger: logging.Logger, level: str, message: str, **fields) -> None:
    """Log a message with arbitrary structured fields."""
    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        message,
        extra={"extra_fields": fields},
    )


def set_correlation_id(correlation_id: str | None = None) -> str:
    cid = correlation_id or str(uuid.uuid4())
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _correlation_id.get()
