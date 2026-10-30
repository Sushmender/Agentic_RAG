"""
backend/tests/test_context_debug.py
Unit tests for Phase B LOG_CONTEXT_DEBUG switch.
"""
from __future__ import annotations


from app.core.config import get_settings
from app.schemas.query import RetrievalResult
from app.services.context_assembly import assemble_context


def test_log_context_debug_setting_exists_and_defaults_false():
    """LOG_CONTEXT_DEBUG is False by default."""
    settings = get_settings()
    assert hasattr(settings, "LOG_CONTEXT_DEBUG")
    assert settings.LOG_CONTEXT_DEBUG is False


def test_context_debug_logging_structure():
    """Verify debug structure logged when LOG_CONTEXT_DEBUG is on."""
    c1 = RetrievalResult(
        chunk_id="chunk_1",
        document_id="doc1",
        chunk_type="text",
        page=1,
        bbox=[0.0, 0.0, 1.0, 1.0],
        text="The quick brown fox jumps over the lazy dog and runs across the wide open fields.",
        similarity_score=0.92,
    )
    c2 = RetrievalResult(
        chunk_id="chunk_2",
        document_id="doc1",
        chunk_type="text",
        page=2,
        bbox=[0.0, 0.0, 1.0, 1.0],
        text="Second chunk content with various information about regional performance.",
        similarity_score=0.88,
    )

    reranked = [c1, c2]
    standalone = "What drove the growth?"
    assembled = assemble_context(candidates=reranked, query=standalone, top_k=1)

    selected_ids = {c.chunk_id for c in assembled.selected_chunks}
    assert len(selected_ids) == 1
    assert "chunk_1" in selected_ids

    debug_chunks = [
        {
            "chunk_id": c.chunk_id,
            "page": c.page,
            "rerank_score": round(c.similarity_score, 4),
            "text_preview": c.text[:80],
            "in_context": c.chunk_id in selected_ids,
        }
        for c in reranked
    ]

    assert len(debug_chunks) == 2
    assert debug_chunks[0]["chunk_id"] == "chunk_1"
    assert debug_chunks[0]["in_context"] is True
    assert debug_chunks[0]["page"] == 1
    assert debug_chunks[0]["rerank_score"] == 0.92
    assert len(debug_chunks[0]["text_preview"]) <= 80

    assert debug_chunks[1]["chunk_id"] == "chunk_2"
    assert debug_chunks[1]["in_context"] is False
    assert debug_chunks[1]["page"] == 2

