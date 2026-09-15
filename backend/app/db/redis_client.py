"""
backend/app/db/redis_client.py
Upstash Redis client for query-answer caching.
Uses Hash data structure: user:{user_id}:qa:{doc_id}
Fields: SHA-256(normalized_query) → JSON(QueryResponse)
Uses SCAN (never KEYS) for cache invalidation patterns.
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Module-level Redis client (initialized on startup)
_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Return the initialized async Redis client."""
    global _redis_client
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _redis_client


async def init_redis() -> None:
    """
    Initialize async Redis client from REDIS_URL (Upstash TLS rediss://).
    Verify connectivity with PING.
    Called once on application startup.
    """
    global _redis_client

    logger.info("Initializing Redis client", url_prefix=settings.REDIS_URL[:20] + "...")

    _redis_client = aioredis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,  # return str instead of bytes
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    # Verify connectivity
    pong = await _redis_client.ping()
    if pong:
        logger.info("Redis connected successfully")
    else:
        logger.error("Redis PING failed")
        raise RuntimeError("Redis connection failed")


async def close_redis() -> None:
    """Close Redis connection gracefully on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


# ── Hash operations (user:{user_id}:qa:{doc_id}) ─────────────────────────────

async def hset(key: str, field: str, value: str) -> None:
    """Set a field in a Redis Hash."""
    await get_redis().hset(key, field, value)  # type: ignore[misc]


async def hget(key: str, field: str) -> Optional[str]:
    """Get a field from a Redis Hash. Returns None if not found."""
    return await get_redis().hget(key, field)  # type: ignore[misc]


async def hgetall(key: str) -> dict[str, str]:
    """Get all fields and values from a Redis Hash."""
    result = await get_redis().hgetall(key)  # type: ignore[misc]
    return result or {}


async def hdel(key: str, *fields: str) -> int:
    """Delete specific fields from a Redis Hash."""
    return await get_redis().hdel(key, *fields)  # type: ignore[misc]


# ── Pattern-based deletion using SCAN ─────────────────────────────────────────

async def scan_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching pattern using SCAN (safe — never uses KEYS).
    Returns count of deleted keys.
    """
    client = get_redis()
    deleted = 0
    cursor = 0

    while True:
        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await client.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break

    logger.info("Redis scan-delete", pattern=pattern, deleted_keys=deleted)
    return deleted


# ── Health check ──────────────────────────────────────────────────────────────

async def is_healthy() -> bool:
    """Check if Redis is accessible."""
    try:
        if _redis_client is None:
            return False
        return bool(await get_redis().ping())
    except Exception as exc:
        logger.error("Redis health check failed", error=str(exc))
        return False
