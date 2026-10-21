"""
backend/tests/test_redis.py
Redis client operations test using isolated in-memory fake client.
"""
import os
import pytest
from app.db import redis_client


@pytest.mark.asyncio
async def test_redis_operations():
    """Verify basic Redis ping, set, and get operations with test isolation."""
    client = redis_client.get_redis()
    assert await client.ping() is True

    await client.set("test_key", "Hello, Redis!")
    val = await client.get("test_key")
    if isinstance(val, bytes):
        val = val.decode("utf-8")
    assert val == "Hello, Redis!"


def main():
    import redis
    from dotenv import load_dotenv

    load_dotenv()
    redis_url = os.getenv("REDIS_URL")
    if redis_url and redis_url.startswith("redis-cli"):
        redis_url = redis_url.split("-u ")[-1].strip()
    if redis_url and "upstash.io" in redis_url and redis_url.startswith("redis://"):
        redis_url = redis_url.replace("redis://", "rediss://", 1)

    print(f"Connecting to Redis URL: {redis_url[:20]}... (masked for security)")
    try:
        client = redis.Redis.from_url(redis_url, ssl_cert_reqs="none")
        print("Pinging Redis...")
        if client.ping():
            print("[SUCCESS] Successfully connected to Redis! Ping returned True.")
        else:
            print("[ERROR] Failed to ping Redis.")
        print("Testing SET/GET operations...")
        client.set("test_key", "Hello, Redis!")
        val = client.get("test_key")
        if val:
            print(f"[SUCCESS] Successfully retrieved value: {val.decode('utf-8')}")
        else:
            print("[ERROR] Failed to retrieve value.")
    except Exception as e:
        print(f"[ERROR] Error connecting to Redis: {e}")


if __name__ == "__main__":
    main()
