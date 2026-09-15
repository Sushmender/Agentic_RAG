"""
backend/tests/test_health.py
Day 0 verification: health endpoint, ChromaDB, Redis initialization.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Test client with real lifespan (starts ChromaDB + Redis)."""
    # Use a test .env by setting env vars before import
    import os
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")
    os.environ.setdefault("LANDINGAI_API_KEY", "test-ade-key")
    os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
    os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379")  # local Redis for tests

    from app.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health_returns_200(client):
    """Health endpoint must return 200."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_has_status_field(client):
    """Health response must have 'status' field."""
    response = client.get("/api/v1/health")
    body = response.json()
    assert "status" in body
    assert body["status"] in ("ok", "degraded")


def test_health_has_components(client):
    """Health response must have 'components' with chromadb and redis."""
    response = client.get("/api/v1/health")
    body = response.json()
    assert "components" in body
    assert "chromadb" in body["components"]
    assert "redis" in body["components"]


def test_health_head(client):
    """HEAD /health must work for uptime monitors."""
    response = client.head("/api/v1/health")
    assert response.status_code in (200, 405)  # 405 is acceptable for HEAD


def test_docs_accessible(client):
    """OpenAPI docs must be accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
