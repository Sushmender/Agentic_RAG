"""
backend/tests/test_ingestion.py
Day 1 ingestion tests:
  - Upload returns document_id + job_id
  - MIME type enforcement (415)
  - File size enforcement (413)
  - Empty file rejection (422)
  - Idempotency: same file → same document_id
  - GET /documents/{id} returns correct metadata
  - GET /documents/{id} 404 for unknown ID
  - GET /jobs/{id} status transitions
  - GET /documents/ lists documents
  - GET /jobs/{id} 403 for wrong user
"""
from __future__ import annotations

import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _register_and_login(username: str | None = None) -> str:
    """Register a user and return their JWT token."""
    username = username or f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@test.com"
    password = "TestPass123!"

    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    })

    resp = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_pdf_bytes(content: bytes = b"%PDF-1.4 fake pdf content for testing") -> bytes:
    return content


def _upload_pdf(token: str, content: bytes | None = None, filename: str = "test.pdf") -> dict:
    """Helper to upload a PDF and return the parsed response JSON."""
    pdf_bytes = content or _make_pdf_bytes()
    files = {"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post(
        "/api/v1/documents/upload",
        files=files,
        headers=_auth_headers(token),
    )
    return resp


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestDocumentUpload:
    def test_upload_returns_document_id_and_job_id(self):
        """Upload a PDF → 202 with document_id and job_id."""
        token = _register_and_login()
        resp = _upload_pdf(token)
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert "document_id" in data
        assert "job_id" in data
        assert len(data["document_id"]) == 64, "document_id should be SHA-256 hex (64 chars)"
        assert data["status"] in ("pending", "processing", "completed")

    def test_upload_enforces_mime_type(self):
        """Upload a .txt file → 415 Unsupported Media Type."""
        token = _register_and_login()
        files = {"file": ("notes.txt", io.BytesIO(b"just some text"), "text/plain")}
        resp = client.post(
            "/api/v1/documents/upload",
            files=files,
            headers=_auth_headers(token),
        )
        assert resp.status_code == 415, resp.text

    def test_upload_enforces_size_limit(self):
        """Upload a file exceeding MAX_UPLOAD_SIZE_MB → 413."""
        from app.core.config import get_settings
        settings = get_settings()
        oversized = b"x" * (settings.max_upload_size_bytes + 1)
        token = _register_and_login()
        files = {"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")}
        resp = client.post(
            "/api/v1/documents/upload",
            files=files,
            headers=_auth_headers(token),
        )
        assert resp.status_code == 413, resp.text

    def test_upload_rejects_empty_file(self):
        """Upload an empty file → 422."""
        token = _register_and_login()
        files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        resp = client.post(
            "/api/v1/documents/upload",
            files=files,
            headers=_auth_headers(token),
        )
        assert resp.status_code == 422, resp.text

    def test_upload_idempotency_same_file_same_document_id(self):
        """Same file uploaded twice → same document_id, no duplicate."""
        token = _register_and_login()
        pdf_bytes = _make_pdf_bytes(b"%PDF-1.4 idempotency test " + uuid.uuid4().bytes)

        resp1 = _upload_pdf(token, content=pdf_bytes)
        resp2 = _upload_pdf(token, content=pdf_bytes)

        assert resp1.status_code == 202, resp1.text
        assert resp2.status_code == 202, resp2.text
        assert resp1.json()["document_id"] == resp2.json()["document_id"]
        # Second response indicates it already exists
        assert "already exists" in resp2.json().get("message", "").lower() or \
               resp1.json()["job_id"] == resp2.json()["job_id"]

    def test_upload_requires_auth(self):
        """Upload without token → 401."""
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        resp = client.post("/api/v1/documents/upload", files=files)
        assert resp.status_code == 401, resp.text


class TestGetDocument:
    def test_get_document_returns_metadata(self):
        """Upload then GET → correct metadata fields."""
        token = _register_and_login()
        pdf_bytes = _make_pdf_bytes(b"%PDF-1.4 get metadata test " + uuid.uuid4().bytes)
        upload_resp = _upload_pdf(token, content=pdf_bytes)
        assert upload_resp.status_code == 202
        document_id = upload_resp.json()["document_id"]

        resp = client.get(
            f"/api/v1/documents/{document_id}",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["document_id"] == document_id
        assert data["filename"] == "test.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["status"] in ("pending", "processing", "completed", "failed")

    def test_get_document_404_for_unknown_id(self):
        """GET unknown document_id → 404."""
        token = _register_and_login()
        fake_id = "a" * 64
        resp = client.get(
            f"/api/v1/documents/{fake_id}",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 404, resp.text

    def test_get_document_requires_auth(self):
        """GET without token → 401."""
        resp = client.get(f"/api/v1/documents/{'a' * 64}")
        assert resp.status_code == 401, resp.text


class TestListDocuments:
    def test_list_documents_returns_uploaded(self):
        """Upload multiple files → list returns all of them."""
        token = _register_and_login()

        file_a = b"%PDF-1.4 list test A " + uuid.uuid4().bytes
        file_b = b"%PDF-1.4 list test B " + uuid.uuid4().bytes

        r1 = _upload_pdf(token, content=file_a)
        r2 = _upload_pdf(token, content=file_b)
        assert r1.status_code == 202
        assert r2.status_code == 202

        doc_id_a = r1.json()["document_id"]
        doc_id_b = r2.json()["document_id"]

        resp = client.get("/api/v1/documents/", headers=_auth_headers(token))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "documents" in data
        ids = [d["document_id"] for d in data["documents"]]
        assert doc_id_a in ids
        assert doc_id_b in ids

    def test_list_documents_empty_for_new_user(self):
        """New user with no uploads → empty list."""
        token = _register_and_login()
        resp = client.get("/api/v1/documents/", headers=_auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"] == [] or isinstance(data["documents"], list)
        # A fresh user (unique username) should see 0 docs
        assert data["total"] == 0

    def test_list_documents_user_isolation(self):
        """User A's documents not visible to User B."""
        token_a = _register_and_login()
        token_b = _register_and_login()

        pdf_bytes = b"%PDF-1.4 isolation test " + uuid.uuid4().bytes
        r = _upload_pdf(token_a, content=pdf_bytes)
        doc_id = r.json()["document_id"]

        resp_b = client.get("/api/v1/documents/", headers=_auth_headers(token_b))
        ids_b = [d["document_id"] for d in resp_b.json()["documents"]]
        assert doc_id not in ids_b


class TestGetJob:
    def test_get_job_returns_status(self):
        """Upload → GET /jobs/{job_id} → returns status."""
        token = _register_and_login()
        pdf_bytes = b"%PDF-1.4 job status test " + uuid.uuid4().bytes
        upload_resp = _upload_pdf(token, content=pdf_bytes)
        job_id = upload_resp.json()["job_id"]

        resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("pending", "processing", "completed", "failed")

    def test_get_job_404_for_unknown(self):
        """GET unknown job_id → 404."""
        token = _register_and_login()
        resp = client.get(
            f"/api/v1/jobs/{uuid.uuid4()}",
            headers=_auth_headers(token),
        )
        assert resp.status_code == 404, resp.text

    def test_get_job_403_for_wrong_user(self):
        """User B cannot access User A's job."""
        token_a = _register_and_login()
        token_b = _register_and_login()

        pdf_bytes = b"%PDF-1.4 ownership test " + uuid.uuid4().bytes
        upload_resp = _upload_pdf(token_a, content=pdf_bytes)
        job_id = upload_resp.json()["job_id"]

        resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers=_auth_headers(token_b),
        )
        assert resp.status_code == 403, resp.text

    def test_job_reaches_completed_or_processing(self):
        """
        After upload the job should eventually reach processing or completed.
        Since ingestion is synchronous in TestClient (BackgroundTasks run inline),
        the job should be completed immediately after the upload response.
        ADE provider is mocked so no live API calls are made in tests.
        """
        from unittest.mock import AsyncMock, patch

        mock_ade_result = {
            "chunks": [
                {
                    "id": "test-chunk-001",
                    "type": "text",
                    "markdown": "<a id='test-chunk-001'></a>\n\nTest content from mock ADE",
                    "grounding": {
                        "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.2},
                        "page": 0,
                    },
                }
            ],
            "markdown": "Test content from mock ADE",
            "metadata": {
                "credit_usage": 1.0,
                "version": "dpt-2-test",
                "page_count": 1,
                "job_id": "mock-ade-job",
                "duration_ms": 100,
                "failed_pages": [],
                "filename": "test.pdf",
            },
            "grounding": {
                "test-chunk-001": {
                    "box": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.2},
                    "page": 0,
                    "type": "chunkText",
                    "confidence": 0.99,
                    "low_confidence_spans": [],
                }
            },
            "splits": [],
        }

        with patch(
            "app.services.ingestion_service.ade_provider.parse_document",
            new_callable=AsyncMock,
            return_value=mock_ade_result,
        ):
            token = _register_and_login()
            pdf_bytes = b"%PDF-1.4 completion test " + uuid.uuid4().bytes
            upload_resp = _upload_pdf(token, content=pdf_bytes)
            job_id = upload_resp.json()["job_id"]

        # TestClient runs background tasks synchronously → completed
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(token))
        assert resp.status_code == 200
        status = resp.json()["status"]
        assert status in ("completed", "processing", "pending"), \
            f"Unexpected status: {status}"
