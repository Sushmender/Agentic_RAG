"""
backend/app/providers/ade.py
LandingAI ADE document parsing provider stub.
Full implementation on Day 2.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import BaseADEProvider

logger = get_logger(__name__)
settings = get_settings()


class ADEProvider(BaseADEProvider):
    """
    LandingAI ADE (Agentic Document Extraction) provider.
    Uses DPT-3 Verity tier (cost-optimized, always).
    Converts documents into structured multimodal chunks:
    text / table / figure with page + bbox provenance.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {settings.LANDINGAI_API_KEY}",
                },
                timeout=httpx.Timeout(120.0),  # ADE can be slow on large docs
            )
        return self._client

    async def parse_document(
        self,
        file_path: str,
        document_id: str,
        tier: str = "verity",
    ) -> dict[str, Any]:
        """
        Parse a document using LandingAI ADE.
        Returns chunks, markdown, credits_used, parser_version.
        Full implementation: Day 2.
        """
        # Stub — returns mock data for Day 0 health checks
        logger.info("ADE parse called (stub)", document_id=document_id, tier=tier)
        return {
            "chunks": [],
            "markdown": "",
            "credits_used": 0.0,
            "parser_version": "stub-0.0",
        }

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
ade_provider = ADEProvider()
