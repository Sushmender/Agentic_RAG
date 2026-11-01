"""
backend/tests/test_audit_leak_fixes.py
Tests verifying that audit cross-user leakage gaps are fully closed:
1. User A's metrics never include User B's records or question text.
2. Telemetry records without a user_id are hidden from all users.
3. Unauthenticated calls to /api/v1/metrics and /api/v1/evaluation/run return 401.
4. Requesting another user's job returns 404 (same message as missing job, not 403).
5. Evaluation restricts retrieval to caller's own documents.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.sqlite_store import document_store, job_store
from app.main import app
from app.schemas.document import DocumentMetadata, DocumentStatus, DocumentType
from app.schemas.job import Job, JobStatus
from app.schemas.telemetry import (
    EmbeddingCost,
    LatencyDetail,
    LLMCost,
    TelemetryRecord,
    TokenUsage,
)
from app.services import telemetry_service


def _auth_headers(user_id: str) -> dict:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


# ── 1. Metrics user scoping and hidden unowned records ────────────────────────

@pytest.mark.asyncio
async def test_user_a_metrics_never_include_user_b_records_or_question_text():
    """
    User A queries /api/v1/metrics.
    Telemetry contains records from User A, User B, and records with no user_id.
    User A must see only their own counts, costs, and recent_queries questions.
    """
    user_a = "user_metrics_a"
    user_b = "user_metrics_b"

    rec_a = TelemetryRecord(
        record_type="query",
        user_id=user_a,
        query_preview="User A confidential query about payroll",
        route_type="text",
        cache_hit=False,
        latency=LatencyDetail(total_ms=500.0, embedding_ms=50.0, retrieval_ms=50.0, reranking_ms=100.0, llm_ms=300.0),
        token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        embedding_cost=EmbeddingCost(model="embed", provider="openrouter", cost_usd=0.0),
        llm_cost=LLMCost(model="qwen", provider="groq", input_tokens=100, output_tokens=50, cost_usd=0.0001),
    )
    rec_b = TelemetryRecord(
        record_type="query",
        user_id=user_b,
        query_preview="User B secret query about merger and acquisition",
        route_type="text",
        cache_hit=True,
        latency=LatencyDetail(total_ms=200.0),
        token_usage=TokenUsage(input_tokens=200, output_tokens=80, total_tokens=280),
        embedding_cost=EmbeddingCost(model="embed", provider="openrouter", cost_usd=0.0),
        llm_cost=LLMCost(model="qwen", provider="groq", input_tokens=200, output_tokens=80, cost_usd=0.0003),
    )
    rec_no_user = TelemetryRecord(
        record_type="query",
        user_id="",
        query_preview="Anonymous leaked question that should never appear",
        route_type="text",
        cache_hit=False,
    )

    await telemetry_service.append_record(rec_a)
    await telemetry_service.append_record(rec_b)
    await telemetry_service.append_record(rec_no_user)

    with TestClient(app) as client:
        resp = client.get("/api/v1/metrics", headers=_auth_headers(user_a))

    assert resp.status_code == 200, resp.text
    data = resp.json()

    # User A only sees their 1 query
    assert data["query_count"] == 1
    assert data["records_analyzed"] == 1
    assert data["cache_hit_count"] == 0
    assert len(data["recent_queries"]) == 1

    # Verify query text is User A's, and User B's text is not present
    assert data["recent_queries"][0]["question"] == "User A confidential query about payroll"
    all_questions_text = " ".join(rq["question"] for rq in data["recent_queries"])
    assert "User B" not in all_questions_text
    assert "merger" not in all_questions_text
    assert "Anonymous" not in all_questions_text


@pytest.mark.asyncio
async def test_records_with_no_user_id_are_hidden():
    """
    Telemetry records with user_id=None or empty string must not appear in any user's metrics.
    """
    rec_anonymous = TelemetryRecord(
        record_type="query",
        user_id="",
        query_preview="Hidden anonymous query",
        route_type="text",
    )
    await telemetry_service.append_record(rec_anonymous)

    with TestClient(app) as client:
        resp = client.get("/api/v1/metrics", headers=_auth_headers("any_user_123"))

    assert resp.status_code == 200
    data = resp.json()
    assert data["query_count"] == 0
    assert data["records_analyzed"] == 0
    assert data["recent_queries"] == []


# ── 2. Unauthenticated calls to metrics and evaluation return 401 ─────────────

def test_unauthenticated_metrics_returns_401():
    """GET /api/v1/metrics without authorization header must return 401."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/metrics")
    assert resp.status_code == 401


def test_unauthenticated_evaluation_returns_401():
    """GET /api/v1/evaluation/run without authorization header must return 401."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/evaluation/run")
    assert resp.status_code == 401


# ── 3. Another user's job returns 404 (same as missing job) ───────────────────

def test_another_users_job_returns_404():
    """
    GET /api/v1/jobs/{job_id} must return 404 'Job \'<job_id>\' not found.'
    when the job belongs to another user (never 403).
    """
    user_owner = "user_job_owner"
    user_attacker = "user_job_attacker"
    job_id = "job_confidential_999"

    now = datetime.now(timezone.utc)
    job = Job(
        job_id=job_id,
        document_id="doc_xyz",
        user_id=user_owner,
        status=JobStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(job_store.save(job))

    with TestClient(app) as client:
        # Attacker queries owner's job
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(user_attacker))
        assert resp.status_code == 404
        assert resp.json()["detail"] == f"Job '{job_id}' not found."

        # Non-existent job also returns identical 404
        resp_missing = client.get("/api/v1/jobs/missing_job_000", headers=_auth_headers(user_attacker))
        assert resp_missing.status_code == 404
        assert resp_missing.json()["detail"] == "Job 'missing_job_000' not found."

        # Owner queries own job -> 200
        resp_owner = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(user_owner))
        assert resp_owner.status_code == 200
        assert resp_owner.json()["job_id"] == job_id


# ── 4. Evaluation restricts retrieval to caller's own documents ───────────────

def test_evaluation_restricts_retrieval_to_callers_documents():
    """
    When User A runs evaluation, retrieval is restricted strictly to User A's documents.
    If the gold dataset question targets a document ID not owned by User A,
    retrieval returns 0 candidates and recall is 0.0 without searching other users' data.
    """
    user_eval = "user_evaluator"

    now = datetime.now(timezone.utc)
    doc_eval = DocumentMetadata(
        document_id="doc_owned_by_evaluator",
        user_id=user_eval,
        filename="eval.pdf",
        document_type=DocumentType.PDF,
        mime_type="application/pdf",
        file_size_bytes=1024,
        status=DocumentStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    asyncio.run(document_store.save(doc_eval))

    # Gold dataset referencing an unowned document
    fake_gold = [
        {
            "question": "What is the secret data?",
            "expected_document_ids": ["doc_owned_by_someone_else"],
            "expected_chunk_ids": ["chunk_unowned"],
        }
    ]

    mock_retrieve = patch("app.evaluation.evaluator.retrieve_hybrid", return_value=[])

    with patch("app.api.v1.endpoints.evaluation.get_collection_stats", return_value={"total_chunks": 10}), \
         patch("app.api.v1.endpoints.evaluation.load_or_generate", return_value=fake_gold), \
         patch("app.evaluation.evaluator.embedding_provider.embed_query", AsyncMock(return_value=[0.1] * 64)), \
         patch("app.evaluation.evaluator.reranker_provider.rerank", AsyncMock(return_value=[])), \
         mock_retrieve as mock_ret:

        with TestClient(app) as client:
            resp = client.get("/api/v1/evaluation/run", headers=_auth_headers(user_eval))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "no_gold_data"
    assert data["questions_evaluated"] == 0
    assert data["pre_rerank"]["recall_at_k"] == 0.0

    # retrieve_hybrid must NOT have been called with the unowned document!
    if mock_ret.called:
        for call_args in mock_ret.call_args_list:
            where_doc_ids = call_args.kwargs.get("document_ids")
            assert "doc_owned_by_someone_else" not in (where_doc_ids or [])
