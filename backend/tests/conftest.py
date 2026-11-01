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
from unittest.mock import AsyncMock

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
    from app.db import redis_client, sqlite_store
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
    from app.db import redis_client, sqlite_store
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


# ── Function-scoped Autouse Fixture: Fake & Guard External Providers ─────────

@pytest.fixture(autouse=True)
def guard_and_fake_external_providers(request, monkeypatch):
    """
    Autouse fixture that:
      1. Bypasses faking and guards when RUN_LIVE_TESTS=1 or the test is marked 'live'.
      2. Fakes provider entry points (ADE, OpenRouter embeddings, OpenRouter reranker,
         Groq LLM, OpenRouter LLM) with realistic return shapes so unit tests do
         not hit live endpoints.
      3. Blocks lower-level network execution methods (ADE _do_parse, OpenRouter post,
         Groq _call_with_retry, Upstash Redis from_url) with clear RuntimeError failures
         if an unmocked network call is ever attempted.
    """
    if os.getenv("RUN_LIVE_TESTS") == "1" or request.node.get_closest_marker("live"):
        yield
        return

    from app.providers.ade import ADEProvider, ade_provider
    from app.providers.groq import GroqProvider, groq_provider
    from app.providers.openrouter import OpenRouterClient, openrouter_client
    from app.providers.openrouter_embedding import embedding_provider
    from app.providers.openrouter_llm import openrouter_llm_provider
    from app.providers.openrouter_reranker import reranker_provider
    import redis.asyncio as aioredis

    # --- Realistic Fakes for Entry Points ---

    async def _fake_ade_parse(self_or_file, file_path=None, document_id=None, tier=None, **kwargs):
        if isinstance(self_or_file, str):
            doc_id = file_path or "fake_doc"
        else:
            doc_id = document_id or "fake_doc"

        return {
            "chunks": [
                {
                    "id": f"chunk-{doc_id[:8]}-001",
                    "type": "text",
                    "markdown": f"<a id='chunk-{doc_id[:8]}-001'></a>\n\nSample parsed text content from document.",
                    "grounding": {
                        "box": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 0.5},
                        "page": 0,
                    },
                }
            ],
            "markdown": "Sample parsed text content from document.",
            "metadata": {
                "credit_usage": 1.0,
                "version": "dpt-2-latest",
                "page_count": 1,
                "duration_ms": 100,
                "job_id": f"job-{doc_id[:8]}",
                "failed_pages": [],
            },
            "grounding": {
                f"chunk-{doc_id[:8]}-001": {
                    "box": {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 0.5},
                    "page": 0,
                    "type": "chunkText",
                    "confidence": 0.99,
                }
            },
            "splits": [],
        }

    async def _fake_embed_passages(texts, *args, **kwargs):
        dim = 2048
        return [[0.1] * dim for _ in texts]

    async def _fake_embed_query(query, *args, **kwargs):
        dim = 2048
        return [0.1] * dim

    async def _fake_rerank(query, candidates, top_k=5, *args, **kwargs):
        results = []
        for i, c in enumerate(candidates[:top_k]):
            item = dict(c)
            item["relevance_score"] = round(1.0 - (i * 0.05), 4)
            results.append(item)
        return results

    async def _fake_groq_generate(prompt, system_prompt=None, max_tokens=1024, temperature=0.0, *args, **kwargs):
        return {
            "content": "Generated test answer based on [Source 1].",
            "model": "qwen/qwen3.8-27b",
            "provider": "groq",
            "input_tokens": 50,
            "output_tokens": 20,
            "total_tokens": 70,
            "cost_usd": 0.00005,
            "latency_ms": 50.0,
        }

    async def _fake_openrouter_llm_generate(prompt, system_prompt=None, max_tokens=1024, temperature=0.0, *args, **kwargs):
        return {
            "content": "Generated fallback test answer based on [Source 1].",
            "model": "nvidia/nemotron-3-super-120b-a12b:free",
            "provider": "openrouter",
            "input_tokens": 50,
            "output_tokens": 20,
            "total_tokens": 70,
            "cost_usd": 0.0,
            "latency_ms": 80.0,
        }

    # Patch entry points on provider instances
    monkeypatch.setattr(ade_provider, "parse_document", _fake_ade_parse)
    monkeypatch.setattr(ADEProvider, "parse_document", _fake_ade_parse)

    monkeypatch.setattr(embedding_provider, "embed_passages", _fake_embed_passages)
    monkeypatch.setattr(embedding_provider, "embed_query", _fake_embed_query)

    monkeypatch.setattr(reranker_provider, "rerank", _fake_rerank)
    monkeypatch.setattr(groq_provider, "generate", _fake_groq_generate)
    monkeypatch.setattr(openrouter_llm_provider, "generate", _fake_openrouter_llm_generate)

    # --- Loud Failure Blockers for Real Network Calls ---

    async def _blocked_ade_do_parse(*args, **kwargs):
        raise RuntimeError("Real network call to LandingAI ADE attempted without RUN_LIVE_TESTS=1")

    async def _blocked_openrouter_post(*args, **kwargs):
        raise RuntimeError("Real network call to OpenRouter attempted without RUN_LIVE_TESTS=1")

    async def _blocked_groq_retry(*args, **kwargs):
        raise RuntimeError("Real network call to Groq attempted without RUN_LIVE_TESTS=1")

    def _blocked_redis_from_url(url, *args, **kwargs):
        if "upstash.io" in str(url).lower():
            raise RuntimeError("Real network call to Upstash Redis attempted without RUN_LIVE_TESTS=1")
        return _global_fake_redis

    monkeypatch.setattr(ADEProvider, "_do_parse", _blocked_ade_do_parse)
    monkeypatch.setattr(OpenRouterClient, "post", _blocked_openrouter_post)
    monkeypatch.setattr(openrouter_client, "post", _blocked_openrouter_post)
    monkeypatch.setattr(GroqProvider, "_call_with_retry", _blocked_groq_retry)
    monkeypatch.setattr(aioredis.Redis, "from_url", _blocked_redis_from_url)

    yield


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    """Skip tests marked with 'live' unless RUN_LIVE_TESTS=1 is set."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        skip_live = pytest.mark.skip(reason="Live test skipped; set RUN_LIVE_TESTS=1 to run")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
