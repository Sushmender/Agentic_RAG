"""
backend/tests/conftest.py
Shared pytest fixtures for the Multimodal RAG test suite.

KEY PURPOSE:
  Redirect all file I/O (uploads, ADE outputs) to a temporary directory
  that is automatically deleted after each test session.
  This prevents test artifacts polluting data/uploads/ and data/ade_outputs/.

HOW IT WORKS:
  - `set_test_env` (session-scoped, autouse) sets UPLOAD_DIR and ADE_OUTPUT_DIR
    environment variables BEFORE any app module is imported. This means the
    lru_cache'd Settings object picks up the temp paths from the start.
  - pytest's `tmp_path_factory` auto-cleans the temp dir after the session.
  - `reset_stores` (function-scoped, autouse) clears in-memory DocumentStore
    and JobStore between every individual test to prevent state leakage.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest


# ── Session-scoped: redirect file I/O to temp dir ─────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def set_test_env(tmp_path_factory: pytest.TempPathFactory):
    """
    Create isolated temp directories for uploads and ADE outputs.
    Sets environment variables BEFORE the app is imported so that the
    lru_cache'd Settings object reads from the temp paths.
    The temp directory is deleted automatically at session end.
    """
    tmp_root = tmp_path_factory.mktemp("rag_test_data", numbered=True)
    upload_dir  = tmp_root / "uploads"
    ade_out_dir = tmp_root / "ade_outputs"
    upload_dir.mkdir(parents=True)
    ade_out_dir.mkdir(parents=True)

    # Patch env vars so Settings picks them up (even if already cached)
    old_upload  = os.environ.get("UPLOAD_DIR")
    old_ade_out = os.environ.get("ADE_OUTPUT_DIR")

    os.environ["UPLOAD_DIR"]     = str(upload_dir)
    os.environ["ADE_OUTPUT_DIR"] = str(ade_out_dir)

    # Force Settings to reload with the new env vars
    try:
        from app.core.config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        s.UPLOAD_DIR     = str(upload_dir)
        s.ADE_OUTPUT_DIR = str(ade_out_dir)
    except Exception:
        pass  # App not yet importable — env vars will be read at import time

    yield {
        "root":    tmp_root,
        "uploads": upload_dir,
        "ade_out": ade_out_dir,
    }

    # ── Cleanup ────────────────────────────────────────────────────────────────
    # Restore original env vars
    if old_upload is None:
        os.environ.pop("UPLOAD_DIR", None)
    else:
        os.environ["UPLOAD_DIR"] = old_upload

    if old_ade_out is None:
        os.environ.pop("ADE_OUTPUT_DIR", None)
    else:
        os.environ["ADE_OUTPUT_DIR"] = old_ade_out

    # Reset settings cache
    try:
        from app.core.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    # Explicitly remove temp tree
    shutil.rmtree(tmp_root, ignore_errors=True)


# ── Function-scoped: patch settings on every individual test ──────────────────

@pytest.fixture(autouse=True)
def patch_settings_paths(set_test_env):
    """
    Ensure the app's cached Settings instance uses the temp paths
    for EVERY test — handles the case where endpoint modules cached
    `settings = get_settings()` at import time.
    """
    from app.core.config import get_settings
    from app.api.v1.endpoints import documents as doc_module

    s = get_settings()
    upload_dir  = set_test_env["uploads"]
    ade_out_dir = set_test_env["ade_out"]

    # Patch the cached singleton
    orig_upload  = s.UPLOAD_DIR
    orig_ade_out = s.ADE_OUTPUT_DIR
    s.UPLOAD_DIR     = str(upload_dir)
    s.ADE_OUTPUT_DIR = str(ade_out_dir)

    # Also patch the module-level `settings` in documents.py
    orig_mod_settings = doc_module.settings
    doc_module.settings = s

    yield

    # Restore
    s.UPLOAD_DIR     = orig_upload
    s.ADE_OUTPUT_DIR = orig_ade_out
    doc_module.settings = orig_mod_settings


# ── Function-scoped: reset in-memory stores between tests ────────────────────

@pytest.fixture(autouse=True)
def reset_stores():
    """
    Clear DocumentStore and JobStore between every test.
    Prevents state leaking from one test into the next.
    """
    from app.db.in_memory_store import document_store, job_store

    document_store._store.clear()
    job_store._store.clear()
    job_store._doc_index.clear()

    yield

    document_store._store.clear()
    job_store._store.clear()
    job_store._doc_index.clear()
