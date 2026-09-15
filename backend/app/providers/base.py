"""
backend/app/providers/base.py
Abstract base classes for all external providers.
Keeps providers/models replaceable — concrete implementations
are injected at runtime via Settings.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class BaseEmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    async def embed_passages(
        self,
        texts: List[str],
        batch_size: int = 16,
    ) -> List[List[float]]:
        """
        Embed a list of passages (document chunks) for indexing.
        Returns list of embedding vectors in the same order as input.
        """
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """
        Embed a single user query for retrieval.
        Some models use different passage vs. query representations.
        """
        ...


class BaseRerankerProvider(ABC):
    """Abstract reranker provider."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: List[dict[str, Any]],
        top_k: int = 5,
    ) -> List[dict[str, Any]]:
        """
        Rerank a list of retrieval candidates given a query.
        Each candidate dict must have at least: chunk_id, text.
        Returns top_k candidates with added 'relevance_score' field, sorted descending.
        """
        ...


class BaseLLMProvider(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """
        Generate a response from the LLM.

        Returns dict with:
            - content: str  (generated text)
            - model: str
            - provider: str
            - input_tokens: int
            - output_tokens: int
            - total_tokens: int
            - cost_usd: float
            - latency_ms: float
        """
        ...


class BaseADEProvider(ABC):
    """Abstract LandingAI ADE document parsing provider."""

    @abstractmethod
    async def parse_document(
        self,
        file_path: str,
        document_id: str,
        tier: str = "verity",
    ) -> dict[str, Any]:
        """
        Parse a document using LandingAI ADE.

        Returns dict with:
            - chunks: list of raw ADE chunk dicts
            - markdown: full document markdown string
            - credits_used: float
            - parser_version: str
        """
        ...
