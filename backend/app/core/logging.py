"""
backend/app/core/logging.py
Structured JSON logging using structlog.
Provides request-scoped context (request_id, job_id, document_id) via contextvars.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping
from uuid import uuid4

import structlog
from structlog.types import EventDict, WrappedLogger

# Context vars for request-scoped IDs
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_job_id_var: ContextVar[str] = ContextVar("job_id", default="")
_document_id_var: ContextVar[str] = ContextVar("document_id", default="")
_user_id_var: ContextVar[str] = ContextVar("user_id", default="")


def set_request_id(request_id: str | None = None) -> str:
    rid = request_id or str(uuid4())
    _request_id_var.set(rid)
    return rid


def set_job_id(job_id: str) -> None:
    _job_id_var.set(job_id)


def set_document_id(document_id: str) -> None:
    _document_id_var.set(document_id)


def set_user_id(user_id: str) -> None:
    _user_id_var.set(user_id)


def _add_context_ids(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject context IDs into every log record."""
    if rid := _request_id_var.get():
        event_dict["request_id"] = rid
    if jid := _job_id_var.get():
        event_dict["job_id"] = jid
    if did := _document_id_var.get():
        event_dict["document_id"] = did
    if uid := _user_id_var.get():
        event_dict["user_id"] = uid
    return event_dict


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """
    Configure structlog for the application.
    In production: JSON output.
    In development (DEBUG): human-readable console output.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        _add_context_ids,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)  # type: ignore[assignment]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    # Quiet noisy libraries
    for lib in ("uvicorn.access", "uvicorn.error", "chromadb", "httpx"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger."""
    return structlog.get_logger(name)
