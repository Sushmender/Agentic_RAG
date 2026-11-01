"""
backend/app/services/embedding_cache.py
Query embedding caching service.
Key: sha256(model name + lowercased, whitespace-collapsed query text).
Storage: Redis with 24 h TTL (86400s). Fallback: in-process LRU (256 entries).
A cache failure must never fail the request.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import List, Optional

from app.core.logging import get_logger
from app.db import redis_client

logger = get_logger(__name__)

_TTL_SECONDS = 86400  # 24 hours


class InMemoryLRUCache:
    """Thread/asyncio-safe in-process LRU cache fallback."""

    def __init__(self, capacity: int = 256) -> None:
        self.capacity = capacity
        self._cache: OrderedDict[str, List[float]] = OrderedDict()

    def get(self, key: str) -> Optional[List[float]]:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: List[float]) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# Singleton in-process LRU fallback
in_memory_lru = InMemoryLRUCache(capacity=256)


def compute_cache_key(model: str, query: str) -> str:
    """
    Compute cache key: sha256(model name + lowercased, whitespace-collapsed query text).
    """
    normalized_query = " ".join(query.strip().lower().split())
    raw = f"{model}:{normalized_query}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def get_cached_embedding(model: str, query: str) -> Optional[List[float]]:
    """
    Retrieve cached query embedding. Checks Redis first; falls back to in-memory LRU.
    A cache failure never fails the request.
    """
    key = compute_cache_key(model, query)
    redis_key = f"embed_cache:{key}"

    # 1. Try Redis
    try:
        client = redis_client.get_redis()
        val = await client.get(redis_key)
        if val is not None:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                # Also populate in-memory LRU for fastest subsequent access
                in_memory_lru.set(key, parsed)
                return parsed
    except Exception as exc:
        logger.debug(
            "Redis query embedding cache read failed, falling back to LRU",
            error=str(exc),
        )

    # 2. Fall back to in-process LRU
    try:
        mem_val = in_memory_lru.get(key)
        if mem_val is not None:
            return mem_val
    except Exception as exc:
        logger.debug("In-memory LRU read failed", error=str(exc))

    return None


async def set_cached_embedding(model: str, query: str, embedding: List[float]) -> None:
    """
    Store query embedding in Redis (24 h TTL) and in-memory LRU.
    A cache failure never fails the request.
    """
    key = compute_cache_key(model, query)
    redis_key = f"embed_cache:{key}"

    # Always write to in-memory LRU
    try:
        in_memory_lru.set(key, embedding)
    except Exception as exc:
        logger.debug("In-memory LRU write failed", error=str(exc))

    # Try Redis
    try:
        client = redis_client.get_redis()
        serialized = json.dumps(embedding)
        await client.set(redis_key, serialized, ex=_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Redis query embedding cache write failed", error=str(exc))
