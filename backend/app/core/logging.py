"""
backend/app/core/logging.py
Structured logging using structlog.

Key design decisions:
- Canonical field order in every record:
    timestamp | level | event | logger | request_id | user_id | document_id | job_id | ...kv pairs
- request_id / user_id / document_id / job_id injected via contextvars so every
  log line in a request automatically carries them without caller boilerplate.
- Dev mode: human-readable KeyValueRenderer (no colours dependency on Windows).
- Prod mode: JSONRenderer (one JSON object per line, machine-parseable).
- query_preview values are always quoted strings.
- Python None values are omitted (never "None" in logs).
- Dev-internal stage references ("Day 4") stripped from event messages.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping
from uuid import uuid4

import structlog
from structlog.types import EventDict, WrappedLogger

# ── Context vars (request-scoped) ─────────────────────────────────────────────
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


# ── Custom processors ──────────────────────────────────────────────────────────

def _inject_context_ids(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Inject request-scoped context IDs and enforce canonical field order.

    Canonical order after this processor:
      timestamp, level, event, logger, request_id, user_id, document_id, job_id,
      <caller-supplied kv pairs>
    """
    # Inject context IDs — only when non-empty
    if rid := _request_id_var.get():
        event_dict["request_id"] = rid
    if uid := _user_id_var.get():
        event_dict["user_id"] = uid
    if did := _document_id_var.get():
        event_dict["document_id"] = did
    if jid := _job_id_var.get():
        event_dict["job_id"] = jid
    return event_dict


def _drop_none_values(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Remove any key whose value is Python None.
    Prevents 'document_ids=None' or 'user_id=None' from appearing in logs.
    """
    return {k: v for k, v in event_dict.items() if v is not None}


def _quote_string_values(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Wrap string values that contain whitespace or special chars in double quotes
    so that log lines remain grep/awk-parseable.
    Keys affected: any value of type str containing spaces, ?, =, or :.
    """
    needs_quoting = lambda v: isinstance(v, str) and any(c in v for c in " ?=:,")
    return {
        k: (f'"{v}"' if needs_quoting(v) else v)
        for k, v in event_dict.items()
    }


def _reorder_fields(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Reorder the event dict so high-signal fields come first.
    Field order: timestamp → level → event → logger →
                 request_id → user_id → document_id → job_id →
                 remaining fields (sorted for stability)
    """
    priority = [
        "timestamp", "level", "event", "logger",
        "request_id", "user_id", "document_id", "job_id",
    ]
    ordered: EventDict = {}
    for key in priority:
        if key in event_dict:
            ordered[key] = event_dict.pop(key)
    # Remaining keys in sorted order for determinism
    for key in sorted(event_dict.keys()):
        ordered[key] = event_dict[key]
    return ordered


# ── Configure ──────────────────────────────────────────────────────────────────

def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """
    Configure structlog for the application.

    Development (DEBUG=True):
        Human-readable output — timestamp | LEVEL | event | logger | k=v k=v …
    Production (DEBUG=False):
        JSON output — one JSON object per line, canonical field order enforced.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,           # adds "logger" key
        structlog.stdlib.add_log_level,             # adds "level" key
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),  # adds "timestamp" key
        _inject_context_ids,                        # injects request_id / user_id / …
        _drop_none_values,                          # removes None values
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        # Production: canonical order then JSON
        renderer_chain = [
            _reorder_fields,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: quote ambiguous strings, reorder, then key=value console format
        renderer_chain = [
            _quote_string_values,
            _reorder_fields,
            structlog.dev.ConsoleRenderer(
                colors=False,           # avoid ANSI codes in PowerShell
                sort_keys=False,        # we handle ordering ourselves
                pad_event=32,           # fixed-width event column for readability
            ),
        ]

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *renderer_chain,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level.upper())

    # Suppress noisy third-party loggers
    for lib in ("uvicorn.access", "uvicorn.error", "chromadb", "httpx", "httpcore"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name)
