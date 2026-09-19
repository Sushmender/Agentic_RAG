"""
backend/app/providers/ade.py
Real LandingAI ADE Parse API integration via raw httpx.

API:  POST https://api.va.landing.ai/v1/ade/parse  (multipart/form-data)
Auth: Authorization: Bearer <LANDINGAI_API_KEY>
Body fields:
  - file:  binary document content (any supported MIME)
  - model: ADE model tier (dpt-2-latest | dpt-3-pro)

Response JSON shape (confirmed from real sample):
  {
    "chunks": [ { "id", "type", "markdown", "grounding": { "box", "page" } } ],
    "markdown": "...",
    "metadata": { "credit_usage", "version", "page_count", "job_id", ... },
    "grounding": { "<chunk_id>": { "box", "page", "type", "confidence", ... } },
    "splits": [ ... ]
  }

Retry policy:
  - 3 attempts, exponential backoff (1s, 2s, 4s)
  - Retries on: httpx.TimeoutException, HTTP 429, HTTP 5xx
  - Does NOT retry on: 4xx client errors (bad file, auth failure)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseADEProvider

logger = get_logger(__name__)
_tenacity_logger = logging.getLogger("tenacity.ade")

settings = get_settings()


def _is_retryable(exc: BaseException) -> bool:
    """Retry on network errors and server-side HTTP failures only."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, httpx.RequestError):
        return True
    return False


class ADEProvider(BaseADEProvider):
    """
    LandingAI ADE (Agentic Document Extraction) provider.
    Converts documents into structured multimodal chunks:
    text / table / figure with page + bbox provenance.

    Model is user-selectable via ADE_MODEL env var:
      dpt-2-latest  — cost-optimized, good for clean/digital docs
      dpt-3-pro     — higher accuracy, use for scanned/complex docs
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {settings.LANDINGAI_API_KEY}"},
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=300.0,   # large docs can take minutes
                    write=60.0,
                    pool=5.0,
                ),
            )
        return self._client

    async def parse_document(
        self,
        file_path: str,
        document_id: str,
        tier: str | None = None,
    ) -> dict[str, Any]:
        """
        Parse a document using the LandingAI ADE API.

        Args:
            file_path:   Absolute path to the uploaded document file.
            document_id: SHA-256 document ID (used only for logging).
            tier:        Override ADE model tier. Falls back to ADE_MODEL env var.

        Returns:
            Full ADE response dict:
            { chunks, markdown, metadata, grounding, splits }

        Raises:
            httpx.HTTPStatusError:  Non-retryable ADE API error (4xx)
            httpx.TimeoutException: ADE timed out after retries exhausted
            FileNotFoundError:      file_path does not exist
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found for ADE parse: {file_path}")

        model = tier or settings.ADE_MODEL
        log = logger.bind(document_id=document_id, model=model, file=path.name)
        log.info("Starting ADE parse", file_size_bytes=path.stat().st_size)

        result = await self._call_with_retry(path=path, model=model, log=log)
        return result

    async def _call_with_retry(
        self,
        *,
        path: Path,
        model: str,
        log: Any,
    ) -> dict[str, Any]:
        """
        Inner retry loop — tenacity doesn't compose cleanly with async methods
        so we wrap the actual HTTP call here.
        """
        attempt = 0
        last_exc: Exception | None = None
        max_attempts = settings.RETRY_MAX_ATTEMPTS
        wait_base = settings.RETRY_WAIT_SECONDS

        while attempt < max_attempts:
            attempt += 1
            try:
                return await self._do_parse(path=path, model=model)
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc):
                    log.error(
                        "ADE non-retryable error",
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise
                wait = wait_base * (2 ** (attempt - 1))
                log.warning(
                    "ADE transient error — retrying",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    wait_seconds=wait,
                    error=str(exc),
                )
                if attempt < max_attempts:
                    await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

    async def _do_parse(self, *, path: Path, model: str) -> dict[str, Any]:
        """
        Single ADE API call. Reads file, posts multipart, returns parsed JSON.
        """
        file_bytes = path.read_bytes()
        mime_type = _guess_mime(path)

        files = {
            "document": (path.name, file_bytes, mime_type),
        }
        data = {"model": model}

        response = await self.client.post(
            settings.LANDINGAI_API_URL,
            files=files,
            data=data,
        )

        if response.status_code >= 400:
            # Log body for debugging before raising
            try:
                body_snippet = response.text[:500]
            except Exception:
                body_snippet = "<unreadable>"
            logger.error(
                "ADE API error",
                status_code=response.status_code,
                body=body_snippet,
                model=model,
            )
            response.raise_for_status()

        result: dict[str, Any] = response.json()

        # Log credit usage from metadata
        meta = result.get("metadata", {})
        logger.info(
            "ADE parse successful",
            model=model,
            chunk_count=len(result.get("chunks", [])),
            credit_usage=meta.get("credit_usage", 0),
            page_count=meta.get("page_count", 0),
            duration_ms=meta.get("duration_ms", 0),
            ade_job_id=meta.get("job_id", ""),
        )
        return result

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def _guess_mime(path: Path) -> str:
    """Simple extension → MIME type map (avoids python-magic dependency)."""
    ext = path.suffix.lower()
    return {
        ".pdf":  "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".doc":  "application/msword",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif":  "image/tiff",
    }.get(ext, "application/octet-stream")


# Module-level singleton
ade_provider = ADEProvider()
