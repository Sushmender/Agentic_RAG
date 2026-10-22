"""
backend/tests/conftest.py
Shared pytest fixtures for the Multimodal RAG test suite.

KEY PURPOSE:
  Redirect ALL persistent storage and network clients (uploads, ADE outputs,
  telemetry JSONL, SQLite database, ChromaDB, and Redis) to isolated
  temporary/in-memory locations that are automatically cleaned up.
  This prevents test artifacts from polluting production files in backend/data
  and the live Upstash Redis instance.
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest


# ── In-Memory Fake Redis with Key Prefix Guard ───────────────────────────────

class FakeRedis:
    """
    In-memory async Redis fake supporting GET/SET/Hash/Scan/Expire operations.
    Enforces a key-prefix guard to prevent state collision and ensure complete
    isolation from real Redis instances.
    """

    def __init__(self, key_prefix: str = "test_guard:"):
        self.key_prefix = key_prefix
        self._data: Dict[str, str] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._ttls: Dict[str, int] = {}

    def _guard_key(self, key: str) -> str:
        if not key.startswith(self.key_prefix):
            return f"{self.key_prefix}{key}"
        return key

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(self._guard_key(key))

    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        k = self._guard_key(key)
        self._data[k] = str(value)
        if ex is not None:
            self._ttls[k] = ex
        return True

    async def hset(self, key: str, field: str, value: Any) -> int:
        k = self._guard_key(key)
        if k not in self._hashes:
            self._hashes[k] = {}
        is_new = field not in self._hashes[k]
        self._hashes[k][field] = str(value)
        return 1 if is_new else 0

    async def hget(self, key: str, field: str) -> Optional[str]:
        k = self._guard_key(key)
        return self._hashes.get(k, {}).get(field)

    async def hgetall(self, key: str) -> Dict[str, str]:
        k = self._guard_key(key)
        return dict(self._hashes.get(k, {}))

    async def hdel(self, key: str, *fields: str) -> int:
        k = self._guard_key(key)
        h = self._hashes.get(k, {})
        count = 0
        for f in fields:
            if f in h:
                del h[f]
                count += 1
        return count

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            k = self._guard_key(key)
            if k in self._data:
                del self._data[k]
                count += 1
            if k in self._hashes:
                del self._hashes[k]
                count += 1
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        k = self._guard_key(key)
        self._ttls[k] = seconds
        return True

    async def scan(self, cursor: int = 0, match: Optional[str] = None, count: int = 100):
        raw_keys = list(self._data.keys()) + list(self._hashes.keys())
        unprefixed = [
            k[len(self.key_prefix):] if k.startswith(self.key_prefix) else k
            for k in raw_keys
        ]
        if match:
            matched = [k for k in unprefixed if fnmatch.fnmatch(k, match)]
        else:
            matched = unprefixed
        return (0, matched)

    async def aclose(self) -> None:
        pass

    def close(self) -> None:
        pass

    def clear(self) -> None:
        self._data.clear()
        self._hashes.clear()
        self._ttls.clear()


# Module-level fake Redis instance shared within test runner
_global_fake_redis = FakeRedis(key_prefix="test_guard:")

# Global temp root for tests configured before collection
_test_tmp_root = Path(tempfile.mkdtemp(prefix="rag_isolated_test_run_"))
_test_upload_dir = _test_tmp_root / "uploads"
_test_ade_out_dir = _test_tmp_root / "ade_outputs"
_test_chroma_dir = _test_tmp_root / "chroma_db"
_test_sqlite_path = _test_tmp_root / "rag.db"
_test_telemetry_path = _test_tmp_root / "telemetry.jsonl"

for d in (_test_upload_dir, _test_ade_out_dir, _test_chroma_dir):
    d.mkdir(parents=True, exist_ok=True)
_test_telemetry_path.write_text("", encoding="utf-8")

# Configure environment variables immediately so import-time settings pick them up
os.environ["UPLOAD_DIR"] = str(_test_upload_dir)
os.environ["ADE_OUTPUT_DIR"] = str(_test_ade_out_dir)
os.environ["CHROMA_DB_PATH"] = str(_test_chroma_dir)
os.environ["SQLITE_DB_PATH"] = str(_test_sqlite_path)
os.environ["TELEMETRY_PATH"] = str(_test_telemetry_path)
os.environ["REDIS_URL"] = "redis://isolated-fake-redis:6379/0"


# ── Safety Guard ─────────────────────────────────────────────────────────────

def _run_safety_guard() -> None:
    """
    Verify at session start that no persistent resource points to real backend/data
    or to real Upstash Redis. If any real resource is detected, abort immediately.
    """
    real_backend_dir = Path(__file__).resolve().parent.parent
    real_data_dir = (real_backend_dir / "data").resolve()

    from app.core.config import get_settings
    from app.db import sqlite_store
    from app.services import telemetry_service

    s = get_settings()
    tel_resolved = telemetry_service._telemetry_path().resolve()
    db_resolved = sqlite_store._get_db_path().resolve()
    chroma_resolved = s.get_chroma_db_path().resolve()
    upload_resolved = s.get_upload_dir().resolve()
    ade_resolved = s.get_ade_output_dir().resolve()

    violations = []

    if tel_resolved == (real_data_dir / "telemetry.jsonl").resolve() or real_data_dir in tel_resolved.parents:
        violations.append(f"Telemetry path resolves to real data: {tel_resolved}")

    if db_resolved == (real_data_dir / "rag.db").resolve() or real_data_dir in db_resolved.parents:
        violations.append(f"SQLite DB path resolves to real data: {db_resolved}")

    if chroma_resolved == (real_data_dir / "chroma_db").resolve() or real_data_dir in chroma_resolved.parents:
        violations.append(f"ChromaDB path resolves to real data: {chroma_resolved}")

    if upload_resolved == (real_data_dir / "uploads").resolve() or real_data_dir in upload_resolved.parents:
        violations.append(f"Upload path resolves to real data: {upload_resolved}")

    if ade_resolved == (real_data_dir / "ade_outputs").resolve() or real_data_dir in ade_resolved.parents:
        violations.append(f"ADE output path resolves to real data: {ade_resolved}")

    if "upstash.io" in s.REDIS_URL.lower():
        violations.append(f"REDIS_URL points to live Upstash instance: {s.REDIS_URL[:25]}...")

    if violations:
        msg = "\n".join(f"  - {v}" for v in violations)
        pytest.exit(f"\n[FATAL] Isolation safety guard aborted test session:\n{msg}", returncode=1)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Pytest hook called before running any tests."""
    # Wire in fake redis
    from app.db import redis_client
    redis_client._redis_client = _global_fake_redis
    redis_client.get_redis = lambda: _global_fake_redis
    redis_client.init_redis = AsyncMock(return_value=None)
    redis_client.close_redis = AsyncMock(return_value=None)

    # Initialize SQLite schema in isolated test DB
    from app.db import sqlite_store
    sqlite_store._DB_PATH = _test_sqlite_path
    asyncio.run(sqlite_store.init_sqlite())

    # Run safety checks
    _run_safety_guard()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up global temp directory after test run."""
    shutil.rmtree(_test_tmp_root, ignore_errors=True)


# ── Session-scoped Fixture ───────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """
    Ensure all settings and singleton paths point to the isolated temp directory
    across the entire test session.
    """
    from app.core.config import get_settings
    from app.db import chromadb_client, redis_client, sqlite_store
    from app.services import telemetry_service

    get_settings.cache_clear()
    s = get_settings()
    s.UPLOAD_DIR = str(_test_upload_dir)
    s.ADE_OUTPUT_DIR = str(_test_ade_out_dir)
    s.CHROMA_DB_PATH = str(_test_chroma_dir)
    s.REDIS_URL = "redis://isolated-fake-redis:6379/0"

    telemetry_service._telemetry_path = lambda: _test_telemetry_path
    sqlite_store._DB_PATH = _test_sqlite_path

    redis_client._redis_client = _global_fake_redis
    redis_client.get_redis = lambda: _global_fake_redis
    redis_client.init_redis = AsyncMock(return_value=None)
    redis_client.close_redis = AsyncMock(return_value=None)

    yield {
        "root": _test_tmp_root,
        "uploads": _test_upload_dir,
        "ade_out": _test_ade_out_dir,
        "chroma": _test_chroma_dir,
        "sqlite": _test_sqlite_path,
        "telemetry": _test_telemetry_path,
        "fake_redis": _global_fake_redis,
    }


# ── Function-scoped Autouse Fixture: Isolate and Reset Stores ─────────────────

@pytest.fixture(autouse=True)
def patch_and_reset_stores(set_test_env, monkeypatch):
    """
    Function-scoped autouse fixture that:
      1. Patches telemetry_service._telemetry_path and sqlite_store._DB_PATH for this test.
      2. Ensures redis_client returns the fake Redis client.
      3. Resets in-memory DocumentStore, JobStore, and embedding LRU cache.
      4. Clears fake Redis state.
      5. Clears tables in the isolated test SQLite database.
    """
    from app.core.config import get_settings
    from app.db import chromadb_client, redis_client, sqlite_store
    from app.db.in_memory_store import document_store, job_store
    from app.services import embedding_cache, telemetry_service
    from app.api.v1.endpoints import documents as doc_module

    s = get_settings()
    s.UPLOAD_DIR = str(set_test_env["uploads"])
    s.ADE_OUTPUT_DIR = str(set_test_env["ade_out"])
    s.CHROMA_DB_PATH = str(set_test_env["chroma"])
    s.REDIS_URL = "redis://isolated-fake-redis:6379/0"

    doc_module.settings = s

    monkeypatch.setattr(telemetry_service, "_telemetry_path", lambda: set_test_env["telemetry"])
    monkeypatch.setattr(sqlite_store, "_DB_PATH", set_test_env["sqlite"])
    monkeypatch.setattr(redis_client, "get_redis", lambda: set_test_env["fake_redis"])
    monkeypatch.setattr(redis_client, "_redis_client", set_test_env["fake_redis"])
    monkeypatch.setattr(redis_client, "init_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_client, "close_redis", AsyncMock(return_value=None))

    # Reset in-memory stores
    document_store._store.clear()
    job_store._store.clear()
    job_store._doc_index.clear()

    # Reset embedding LRU cache and fake redis
    embedding_cache.in_memory_lru.clear()
    set_test_env["fake_redis"].clear()

    # Clear SQLite tables in isolated test DB
    async def _clear_db():
        async with aiosqlite.connect(set_test_env["sqlite"]) as db:
            await db.execute("DELETE FROM documents")
            await db.execute("DELETE FROM jobs")
            await db.execute("DELETE FROM users")
            await db.commit()

    asyncio.run(_clear_db())

    yield

    # Teardown reset
    document_store._store.clear()
    job_store._store.clear()
    job_store._doc_index.clear()
    embedding_cache.in_memory_lru.clear()
    set_test_env["fake_redis"].clear()


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    """Skip tests marked with 'live' unless RUN_LIVE_TESTS=1 is set."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        skip_live = pytest.mark.skip(reason="Live test skipped; set RUN_LIVE_TESTS=1 to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
