"""
backend/app/services/cache_service.py
Day 6: Redis Query-Answer Cache.

Cache structure:
  Key  : user:{user_id}:qa:{document_id}   (Redis Hash)
  Field: SHA-256(normalize(query))          (str)
  Value: JSON-serialized QueryResponse      (str)

Special document key when no document filter is applied:
  user:{user_id}:qa:__all__

TTL is applied to the whole hash key (all Q&As for user+doc expire together).
TTL is refreshed (EXPIRE) on every write.

All public functions degrade gracefully when Redis is unavailable --
they return None / skip silently and log the error.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db import redis_client

logger = get_logger(__name__)
settings = get_settings()

# Sentinel document ID used when no document_ids filter is applied
_ALL_DOCS_SENTINEL = "__all__"


# -- Key helpers ---------------------------------------------------------------

def _cache_key(user_id: str, document_id: str) -> str:
    """Redis Hash key for user+document Q&A pairs."""
    return f"user:{user_id}:qa:{document_id}"


def _field_key(query: str) -> str:
    """
    Stable field key for a query.
    Normalise: lowercase + strip whitespace -> SHA-256 hex digest.
    This ensures "What is revenue?" and "what is revenue?" share the same cache slot.
    """
    normalised = query.lower().strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _doc_key(document_ids: list[str] | None) -> str:
    """
    Map the (possibly absent) document_ids filter to a single cache dimension.

    - None / empty list  -> __all__  (query searched all docs)
    - Single doc         -> doc_id
    - Multiple docs      -> __all__  (treat as global query)
    """
    if not document_ids:
        return _ALL_DOCS_SENTINEL
    if len(document_ids) == 1:
        return document_ids[0]
    return _ALL_DOCS_SENTINEL


# -- Public API ----------------------------------------------------------------

async def get_cached_response(
    user_id: str,
    document_ids: "list[str] | None",
    query: str,
) -> "Optional[object]":
    """
    Look up a cached QueryResponse.

    Returns:
        QueryResponse with cache_hit=True if found, else None.
    Degrades gracefully if Redis is unavailable.
    """
    from app.schemas.query import QueryResponse

    try:
        key = _cache_key(user_id, _doc_key(document_ids))
        field = _field_key(query)
        raw = await redis_client.hget(key, field)

        if raw is None:
            logger.info(
                "Cache MISS",
                user_id=user_id,
                doc_key=_doc_key(document_ids),
            )
            return None

        response = QueryResponse.model_validate_json(raw)
        response.cache_hit = True
        logger.info(
            "Cache HIT",
            user_id=user_id,
            doc_key=_doc_key(document_ids),
        )
        return response

    except Exception as exc:
        logger.warning(
            "Cache get failed -- skipping (Redis unavailable?)",
            user_id=user_id,
            error=str(exc),
        )
        return None


async def set_cached_response(
    user_id: str,
    document_ids: "list[str] | None",
    query: str,
    response: "object",
) -> None:
    """
    Store a QueryResponse in the cache.

    - Serialises response to JSON
    - Sets the hash field
    - Refreshes TTL on the hash key (EXPIRE)

    Degrades gracefully if Redis is unavailable.
    """
    try:
        doc_key = _doc_key(document_ids)
        key = _cache_key(user_id, doc_key)
        field = _field_key(query)

        # Store with cache_hit=False so the reader can stamp it True on retrieval
        payload = response.model_copy(update={"cache_hit": False})
        raw = payload.model_dump_json()

        await redis_client.hset(key, field, raw)

        # Refresh TTL on every write
        client = redis_client.get_redis()
        await client.expire(key, settings.CACHE_TTL_SECONDS)

        logger.info(
            "Cache SET",
            user_id=user_id,
            doc_key=doc_key,
            ttl_seconds=settings.CACHE_TTL_SECONDS,
        )

    except Exception as exc:
        logger.warning(
            "Cache set failed -- skipping (Redis unavailable?)",
            user_id=user_id,
            error=str(exc),
        )


async def invalidate_document_cache(document_id: str) -> int:
    """
    Invalidate ALL cached Q&As that involve this document, for ALL users.

    Pattern: *:qa:{document_id}
    Uses SCAN (never KEYS) for safety in production.

    Returns: number of Redis keys deleted.
    Degrades gracefully if Redis is unavailable.
    """
    try:
        pattern = f"*:qa:{document_id}"
        deleted = await redis_client.scan_delete_pattern(pattern)
        logger.info(
            "Cache invalidated for document",
            document_id=document_id,
            keys_deleted=deleted,
        )
        return deleted
    except Exception as exc:
        logger.warning(
            "Cache invalidation failed -- Redis unavailable?",
            document_id=document_id,
            error=str(exc),
        )
        return 0


async def list_user_qa_pairs(
    user_id: str,
    document_ids: "list[str] | None",
) -> "list[dict]":
    """
    Return all cached Q&A field->value pairs for a user+document combination.

    Returns a list of dicts: [{"field_key": str, "response": QueryResponse}, ...]
    Returns empty list if nothing cached or Redis unavailable.

    Used by GET /query/history endpoint.
    """
    from app.schemas.query import QueryResponse

    try:
        doc_key = _doc_key(document_ids)
        key = _cache_key(user_id, doc_key)
        raw_pairs = await redis_client.hgetall(key)

        results = []
        for field, raw in raw_pairs.items():
            try:
                response = QueryResponse.model_validate_json(raw)
                response.cache_hit = True
                results.append({"field_key": field, "response": response})
            except Exception:
                pass  # Skip malformed cache entries

        logger.info(
            "Listed Q&A cache pairs",
            user_id=user_id,
            doc_key=doc_key,
            pairs_found=len(results),
        )
        return results

    except Exception as exc:
        logger.warning(
            "Cache list failed -- Redis unavailable?",
            user_id=user_id,
            error=str(exc),
        )
        return []
