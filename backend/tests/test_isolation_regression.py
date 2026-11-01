"""
backend/tests/test_isolation_regression.py
Regression tests ensuring test executions do not pollute real persistent data.
"""
from __future__ import annotations

from pathlib import Path
import pytest
from app.schemas.telemetry import TelemetryRecord
from app.services import telemetry_service


@pytest.mark.asyncio
async def test_telemetry_write_does_not_touch_real_telemetry_or_db():
    """
    Regression test: executing a telemetry-writing code path must append to
    the isolated temporary telemetry file and leave the real data/telemetry.jsonl
    and data/rag.db completely untouched (same size and modification time).
    """
    backend_dir = Path(__file__).resolve().parent.parent
    real_telemetry = backend_dir / "data" / "telemetry.jsonl"
    real_db = backend_dir / "data" / "rag.db"

    assert real_telemetry.exists(), f"Real telemetry file not found at {real_telemetry}"
    assert real_db.exists(), f"Real database file not found at {real_db}"

    # Record initial states
    initial_tel_stat = real_telemetry.stat()
    initial_tel_size = initial_tel_stat.st_size
    initial_tel_mtime = initial_tel_stat.st_mtime_ns

    initial_db_stat = real_db.stat()
    initial_db_size = initial_db_stat.st_size
    initial_db_mtime = initial_db_stat.st_mtime_ns

    # Call telemetry-writing code path
    record = TelemetryRecord(
        record_type="query",
        user_id="isolation-regression-test-user",
        query_preview="Regression test isolation query verification",
        route_type="text",
        cache_hit=False,
    )
    await telemetry_service.append_record(record)

    # Verify that the test isolated telemetry file received the write
    test_tel_path = telemetry_service._telemetry_path()
    assert test_tel_path != real_telemetry
    assert test_tel_path.exists()
    assert "isolation-regression-test-user" in test_tel_path.read_text(encoding="utf-8")

    # Verify real telemetry file was strictly untouched
    after_tel_stat = real_telemetry.stat()
    assert after_tel_stat.st_size == initial_tel_size, (
        f"Real telemetry file size changed! Before: {initial_tel_size}, After: {after_tel_stat.st_size}"
    )
    assert after_tel_stat.st_mtime_ns == initial_tel_mtime, (
        f"Real telemetry file mtime changed! Before: {initial_tel_mtime}, After: {after_tel_stat.st_mtime_ns}"
    )

    # Verify real DB was strictly untouched
    after_db_stat = real_db.stat()
    assert after_db_stat.st_size == initial_db_size, (
        f"Real SQLite DB size changed! Before: {initial_db_size}, After: {after_db_stat.st_size}"
    )
    assert after_db_stat.st_mtime_ns == initial_db_mtime, (
        f"Real SQLite DB mtime changed! Before: {initial_db_mtime}, After: {after_db_stat.st_mtime_ns}"
    )
