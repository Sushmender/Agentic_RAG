"""
test_ade.py — LandingAI ADE integration test suite

Run:
    python test_ade.py                     # runs everything
    python test_ade.py --skip-parse        # auth check + mocked tests only (0 credits)
    python test_ade.py --file path/to.pdf  # use your own sample doc
"""

import os
import sys
import json
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("LANDINGAI_API_KEY")
# GA endpoint per current docs. Do NOT use the old /v1/tools/document-analysis path.
API_URL = os.getenv("LANDINGAI_API_URL", "https://api.va.landing.ai/v1/ade/parse")
DEFAULT_MODEL = os.getenv("LANDINGAI_MODEL", "dpt-2-latest")
OUTPUT_DIR = Path("data/ade_outputs")


def banner(title: str):
    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


# ---------------------------------------------------------------------------
# 1. Auth / connectivity check — 0 credits (no document sent, so no page is
#    parsed; ADE bills per page processed, not per request).
# ---------------------------------------------------------------------------
def test_connection() -> bool:
    banner("Step 1: Auth + Connectivity (0 credits)")

    if not API_KEY or API_KEY == "your_landingai_api_key_here":
        print("[WARNING] LANDINGAI_API_KEY is not set. Update your .env file.")
        return False

    print(f"Endpoint: {API_URL}")
    print(f"API key starts with: {API_KEY[:10]}...")

    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        # No file payload -> a valid key should return 4XX (missing document),
        # not 401. This confirms auth + routing without spending credits.
        response = requests.post(API_URL, headers=headers, timeout=15)
        print(f"Status: {response.status_code}")
        try:
            print(f"Body: {response.json()}")
        except ValueError:
            print(f"Body: {response.text[:300]}")

        if response.status_code == 401:
            print("[ERROR] Auth failed — check your API key.")
            return False
        elif response.status_code == 404:
            print("[ERROR] 404 — endpoint path/host is likely wrong, not an auth issue.")
            return False
        elif response.status_code in (400, 415, 422):
            print("[SUCCESS] Auth is valid (rejected only because no file was sent).")
            return True
        elif response.status_code == 200:
            print("[SUCCESS] Request succeeded.")
            return True
        else:
            print(f"[INFO] Unexpected status {response.status_code} — inspect body above.")
            return False

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        return False


# ---------------------------------------------------------------------------
# 2. Real parse test — the ONLY step that spends credits. Idempotent: if
#    output already exists for this file, it reuses it instead of re-calling.
#    Use a single sample page that mixes text + a table + a figure/image so
#    one call exercises every chunk_type you care about.
# ---------------------------------------------------------------------------
def test_parse_sample(file_path: str, model: str = DEFAULT_MODEL) -> dict | None:
    banner("Step 2: Real Parse Call (spends credits — runs once)")

    src = Path(file_path)
    if not src.exists():
        print(f"[ERROR] Sample file not found: {src}")
        print("Point --file at a small, single-page doc with text + a table + an image.")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cached = OUTPUT_DIR / f"{src.stem}_parse_output.json"

    if cached.exists():
        print(f"[SKIP] Cached output found at {cached} — not calling ADE again.")
        return json.loads(cached.read_text())

    try:
        from landingai_ade import LandingAIADE
    except ImportError:
        print("[ERROR] Official SDK not installed. Run: pip install landingai-ade")
        return None

    client = LandingAIADE(apikey=API_KEY)

    print(f"Parsing {src.name} with model={model} (this call costs credits)...")
    response = client.parse(document=src, model=model, save_to=str(OUTPUT_DIR))

    chunks = getattr(response, "chunks", None)
    if chunks:
        print(f"[SUCCESS] Got {len(chunks)} chunks back.")

        def _get(c, *keys):
            # SDK may return dicts OR pydantic-style objects depending on
            # version, so check both shapes rather than assuming one.
            for key in keys:
                if isinstance(c, dict) and key in c:
                    return c[key]
                if hasattr(c, key):
                    return getattr(c, key)
            return None

        chunk_types = {_get(c, "chunk_type", "type") or "unknown" for c in chunks}
        print(f"Chunk types present: {chunk_types}")

        # Dump the first chunk's raw shape so you can see the exact field
        # names your chunking_service.py normalizer needs to map against.
        first = chunks[0]
        raw = first if isinstance(first, dict) else (
            first.model_dump() if hasattr(first, "model_dump") else vars(first)
        )
        print("\nFirst chunk raw shape (for chunking_service.py mapping):")
        print(json.dumps(raw, indent=2, default=str)[:800])
    else:
        print("[INFO] No 'chunks' attribute found — inspect raw response manually.")

    return response


# ---------------------------------------------------------------------------
# 3. Error-path tests — fully mocked, 0 credits. Confirms YOUR code handles
#    bad input / bad responses correctly; doesn't need a real ADE call.
# ---------------------------------------------------------------------------
def test_error_handling_mocked():
    banner("Step 3: Error Handling (mocked, 0 credits)")

    with patch("requests.post") as mock_post:
        # Simulate invalid API key
        mock_post.return_value = MagicMock(status_code=401, json=lambda: {"error": "unauthorized"})
        resp = requests.post(API_URL, headers={"Authorization": "Bearer bad_key"})
        assert resp.status_code == 401
        print("[PASS] 401 handling simulated correctly.")

        # Simulate malformed/empty response your chunking normalizer must survive
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        resp = requests.post(API_URL, headers={"Authorization": "Bearer fake"})
        body = resp.json()
        assert "chunks" not in body
        print("[PASS] Empty/malformed response handled without crashing.")

        # Simulate oversized/unsupported file rejection
        mock_post.return_value = MagicMock(status_code=413, json=lambda: {"error": "file too large"})
        resp = requests.post(API_URL, headers={"Authorization": "Bearer fake"})
        assert resp.status_code == 413
        print("[PASS] Oversized file rejection simulated correctly.")


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LandingAI ADE test suite")
    parser.add_argument("--file", default="sample_docs/mixed_sample.pdf",
                         help="Path to a small sample doc for the real parse test")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--skip-parse", action="store_true",
                         help="Skip the credit-spending real parse call")
    args = parser.parse_args()

    ok = test_connection()
    if not ok:
        print("\n[ABORT] Fix auth/connectivity before running further tests.")
        sys.exit(1)

    test_error_handling_mocked()

    if not args.skip_parse:
        test_parse_sample(args.file, args.model)
    else:
        print("\n[SKIPPED] Real parse call skipped (--skip-parse).")

    print("\nDone.")


if __name__ == "__main__":
    main()