"""
backend/scripts/diag_embed.py
Phase 1 diagnostic script -- investigates why live query embeddings fail.

Usage (from backend/ dir):
    .venv\\Scripts\\python.exe scripts/diag_embed.py

Limits: at most 40 small embedding requests + 1 rerank in total.
NEVER logs API keys or secret values.
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

# Load settings BEFORE importing app modules
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.core.config import get_settings

cfg = get_settings()

# Constants
EMBED_BASE_URL = cfg.OPENROUTER_BASE_URL
EMBED_MODEL    = cfg.EMBEDDING_MODEL
RERANK_MODEL   = cfg.RERANKER_MODEL
EMBED_TIMEOUT  = cfg.EMBED_QUERY_TIMEOUT_S

TEST_QUERY = "What drove the 31% growth in the Southeast region?"
PROXY_VARS = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]

TOTAL_REQUEST_COUNT = 0   # global counter -- cap at 40
MAX_REQUESTS        = 40


# Helpers

def _count_request(n: int = 1) -> bool:
    """Return True if allowed, False if quota exceeded."""
    global TOTAL_REQUEST_COUNT
    TOTAL_REQUEST_COUNT += n
    if TOTAL_REQUEST_COUNT > MAX_REQUESTS:
        print(f"\n[QUOTA] Reached {MAX_REQUESTS} request cap -- stopping here.")
        return False
    return True


def _safe_headers(resp: httpx.Response) -> Dict[str, str]:
    """Return only rate-limit / retry-after headers -- never Authorization."""
    keep = {}
    for k, v in resp.headers.items():
        lk = k.lower()
        if any(x in lk for x in ("rate", "retry", "x-ratelimit", "limit", "remaining", "reset")):
            keep[k] = v
    return keep


def _fmt_ms(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms/1000:.2f} s"


def _cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _raw_headers() -> Dict[str, str]:
    """Auth headers -- key is used but NEVER printed."""
    return {
        "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://multimodal-rag-app",
        "X-Title": "Multimodal RAG (diag)",
    }


async def _raw_embed(
    client: httpx.AsyncClient,
    text: str,
    timeout: float,
    input_type: str = "query",
) -> Tuple[Optional[List[float]], float, Optional[int], Optional[str], Dict[str, str]]:
    """
    Raw httpx embedding call.
    Returns: (vector_or_None, elapsed_ms, status_code, provider_name, rl_headers)
    """
    payload = {
        "model": EMBED_MODEL,
        "input": [text],
        "input_type": input_type,
    }
    t0 = time.monotonic()
    try:
        r = await client.post("/embeddings", json=payload, timeout=timeout)
        elapsed_ms = (time.monotonic() - t0) * 1000
        rl_headers  = _safe_headers(r)
        try:
            body = r.json()
        except Exception:
            body = {}
        status = r.status_code
        r.raise_for_status()
        data = body.get("data", [])
        vector = data[0].get("embedding") if data else None
        provider = (
            body.get("provider")
            or body.get("x-provider")
            or (body.get("model", EMBED_MODEL).split("/")[0] if "/" in body.get("model", "") else None)
        )
        return vector, elapsed_ms, status, provider, rl_headers
    except httpx.TimeoutException as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return None, elapsed_ms, None, str(type(exc).__name__), {}
    except httpx.HTTPStatusError as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        rl_headers  = _safe_headers(exc.response)
        return None, elapsed_ms, exc.response.status_code, None, rl_headers
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        return None, elapsed_ms, None, str(type(exc).__name__), {}


# Print config

def print_config() -> None:
    print("=" * 70)
    print("PHASE 1 -- EMBEDDING DIAGNOSTIC")
    print("=" * 70)
    print(f"\n[CONFIG]")
    print(f"  Embedding base URL        : {EMBED_BASE_URL}")
    print(f"  Embedding model           : {EMBED_MODEL}")
    print(f"  Reranker model            : {RERANK_MODEL}")
    print(f"  EMBED_QUERY_TIMEOUT_S     : {cfg.EMBED_QUERY_TIMEOUT_S}")
    print(f"  EMBED_QUERY_MAX_ATTEMPTS  : {cfg.EMBED_QUERY_MAX_ATTEMPTS}")
    print(f"  EMBED_QUERY_BACKOFF_S     : {cfg.EMBED_QUERY_BACKOFF_S}")
    print(f"  EMBED_QUERY_HEDGE_AFTER_S : {cfg.EMBED_QUERY_HEDGE_AFTER_S}")
    print(f"  EMBED_QUERY_HEDGE_ENABLED : {cfg.EMBED_QUERY_HEDGE_ENABLED}")
    print(f"  TIMEOUT_SECONDS           : {cfg.TIMEOUT_SECONDS}")

    print(f"\n  httpx version      : {httpx.__version__}")
    from app.providers.openrouter import openrouter_client
    cl = openrouter_client.client
    transport_name = type(getattr(cl, "_transport", None)).__name__
    print(f"  httpx transport    : {transport_name}")
    print(f"  HTTP/2 (inferred)  : {'possibly yes' if 'http2' in transport_name.lower() else 'no (AsyncHTTPTransport default)'}")

    found_proxy = [v for v in PROXY_VARS if os.environ.get(v)]
    if found_proxy:
        print(f"\n  Proxy env vars set : {found_proxy}  (values hidden)")
    else:
        print(f"\n  Proxy env vars     : none set")

    key_set = bool(cfg.OPENROUTER_API_KEY and cfg.OPENROUTER_API_KEY != "")
    print(f"\n  OPENROUTER_API_KEY : {'SET (not shown)' if key_set else 'NOT SET!'}")
    print()


# Test A: raw sequential

async def test_a() -> List[Dict[str, Any]]:
    print("\n" + "-" * 60)
    print("TEST A -- Raw sequential (6 calls, fresh client each time)")
    print("-" * 60)
    rows = []
    for i in range(1, 7):
        if not _count_request():
            break
        async with httpx.AsyncClient(
            base_url=EMBED_BASE_URL,
            headers=_raw_headers(),
        ) as client:
            vector, ms, status, provider, rl = await _raw_embed(client, TEST_QUERY, EMBED_TIMEOUT)
        ok   = vector is not None
        size = len(vector) if vector else 0
        row  = {"call": i, "ok": ok, "ms": ms, "status": status,
                "provider": provider, "vec_len": size, "rl": rl}
        rows.append(row)
        print(f"  A{i}: {'OK' if ok else 'FAIL'} | status={status} | {_fmt_ms(ms)} | "
              f"vec_len={size} | provider={provider} | rl_hdrs={rl or 'none'}")

    return rows


# Test B: app provider path (no hedging, no cache, no retry)

async def test_b() -> List[Dict[str, Any]]:
    print("\n" + "-" * 60)
    print("TEST B -- App provider path (no hedging, no cache, no retry, 6 calls)")
    print("-" * 60)
    from app.providers.openrouter import openrouter_client as or_client

    rows = []
    for i in range(1, 7):
        if not _count_request():
            break
        t0 = time.monotonic()
        rl_hdrs: Dict[str, str] = {}
        try:
            payload: Dict[str, Any] = {
                "model": EMBED_MODEL,
                "input": [TEST_QUERY],
                "input_type": "query",
            }
            response = await or_client.post("/embeddings", payload, timeout=EMBED_TIMEOUT)
            ms = (time.monotonic() - t0) * 1000
            data = response.get("data", [])
            vec  = data[0].get("embedding") if data else None
            row  = {"call": i, "ok": True, "ms": ms, "vec_len": len(vec) if vec else 0,
                    "status": 200}
            print(f"  B{i}: OK | {_fmt_ms(ms)} | vec_len={len(vec) if vec else 0}")
        except httpx.HTTPStatusError as exc:
            ms = (time.monotonic() - t0) * 1000
            rl_hdrs = _safe_headers(exc.response)
            row = {"call": i, "ok": False, "ms": ms, "status": exc.response.status_code, "rl": rl_hdrs}
            print(f"  B{i}: FAIL | status={exc.response.status_code} | {_fmt_ms(ms)} | rl_hdrs={rl_hdrs}")
        except Exception as exc:
            ms = (time.monotonic() - t0) * 1000
            row = {"call": i, "ok": False, "ms": ms, "exc": type(exc).__name__}
            print(f"  B{i}: FAIL | exc={type(exc).__name__} | {_fmt_ms(ms)}")
        rows.append(row)

    return rows


# Step 4: diff between A and B headers/body

async def diff_a_vs_b() -> None:
    print("\n" + "-" * 60)
    print("STEP 4 -- Keys-only diff: raw (A) vs app-path (B) request")
    print("-" * 60)

    raw_body = {
        "model": EMBED_MODEL,
        "input": [TEST_QUERY],
        "input_type": "query",
    }
    raw_headers_keys = sorted(_raw_headers().keys())

    from app.providers.openrouter import openrouter_client as or_client
    app_hdrs_keys = sorted(k for k in or_client._auth_headers().keys())

    app_body = {
        "model": EMBED_MODEL,
        "input": [TEST_QUERY],
        "input_type": "query",
    }

    print(f"\n  Raw body keys  : {sorted(raw_body.keys())}")
    print(f"  App body keys  : {sorted(app_body.keys())}")

    body_diff = set(raw_body.keys()) ^ set(app_body.keys())
    print(f"  Body key diff  : {body_diff or 'NONE (identical)'}")

    print(f"\n  Raw header keys: {raw_headers_keys}")
    print(f"  App header keys: {app_hdrs_keys}")
    hdr_diff = set(raw_headers_keys) ^ set(app_hdrs_keys)
    print(f"  Header key diff: {hdr_diff or 'NONE (identical)'}")

    print(f"\n  Raw model      : {raw_body['model']}")
    print(f"  App model      : {app_body['model']}")
    print(f"  input_type     : {raw_body['input_type']} vs {app_body['input_type']}")
    print()


# Test C: content diversity

async def test_c() -> None:
    print("\n" + "-" * 60)
    print("TEST C -- Content diversity (3 queries x 3 = 9 calls, raw)")
    print("-" * 60)
    queries = [
        "and what drove it?",
        "What drove the 31% growth in the Southeast region?",
        "hello world",
    ]
    for q in queries:
        results = []
        for _ in range(3):
            if not _count_request():
                return
            async with httpx.AsyncClient(
                base_url=EMBED_BASE_URL,
                headers=_raw_headers(),
            ) as client:
                vec, ms, status, prov, rl = await _raw_embed(client, q, EMBED_TIMEOUT)
            results.append((vec is not None, ms, status))
        oks = sum(1 for ok, _, _ in results if ok)
        avms = sum(ms for _, ms, _ in results) / len(results)
        print(f"  Query '{q[:50]}': {oks}/3 ok, avg={_fmt_ms(avms)}, statuses={[s for _, _, s in results]}")


# Test D: concurrency

async def test_d() -> None:
    print("\n" + "-" * 60)
    print("TEST D -- Concurrency (2 concurrent calls x 3 rounds = 6 calls)")
    print("-" * 60)
    seq_times = []

    async def _one(label: str) -> Dict[str, Any]:
        if not _count_request():
            return {"label": label, "ok": False, "ms": 0, "reason": "quota"}
        async with httpx.AsyncClient(
            base_url=EMBED_BASE_URL,
            headers=_raw_headers(),
        ) as client:
            vec, ms, status, _, _ = await _raw_embed(client, TEST_QUERY, EMBED_TIMEOUT)
        return {"label": label, "ok": vec is not None, "ms": ms, "status": status}

    for round_n in range(1, 4):
        t0 = time.monotonic()
        r1, r2 = await asyncio.gather(_one(f"R{round_n}a"), _one(f"R{round_n}b"))
        wall_ms = (time.monotonic() - t0) * 1000
        seq_times.append((r1["ms"], r2["ms"], wall_ms))
        print(f"  Round {round_n}: a={_fmt_ms(r1['ms'])} ok={r1['ok']} | "
              f"b={_fmt_ms(r2['ms'])} ok={r2['ok']} | wall={_fmt_ms(wall_ms)}")

    if seq_times:
        avg_a  = sum(a for a, _, _ in seq_times) / len(seq_times)
        avg_w  = sum(w for _, _, w in seq_times) / len(seq_times)
        print(f"\n  Avg single={_fmt_ms(avg_a)}, avg wall={_fmt_ms(avg_w)}")
        ratio = avg_w / max(avg_a, 1)
        print(f"  Concurrency ratio wall/single = {ratio:.2f} "
              f"({'no significant slowdown' if ratio < 1.5 else 'SLOWED DOWN'})")


# Test E: idle gaps / keep-alive

async def test_e() -> None:
    print("\n" + "-" * 60)
    print("TEST E -- Idle gaps: 1 reused client, 3 calls with 15 s pauses")
    print("-" * 60)

    # Test with HTTP/1.1 only (httpx[http2] not required)
    label = "HTTP/1.1"
    print(f"\n  [{label}]")
    try:
        transport = httpx.AsyncHTTPTransport()
        async with httpx.AsyncClient(
            base_url=EMBED_BASE_URL,
            headers=_raw_headers(),
            transport=transport,
        ) as client:
            for call_n in range(1, 4):
                if not _count_request():
                    return
                vec, ms, status, _, _ = await _raw_embed(client, TEST_QUERY, EMBED_TIMEOUT)
                print(f"  E{call_n} [{label}]: {'ok' if vec else 'FAIL'} | {_fmt_ms(ms)} | status={status}")
                if call_n < 3:
                    print(f"  ... sleeping 15 s ...")
                    await asyncio.sleep(15)
    except Exception as exc:
        print(f"  E [{label}] setup error: {exc}")


# Test F: control calls (reranker + key info)

async def test_f() -> None:
    print("\n" + "-" * 60)
    print("TEST F -- Control: reranker + OpenRouter key-info endpoint")
    print("-" * 60)

    # F1: reranker
    if _count_request():
        t0 = time.monotonic()
        payload = {
            "model": RERANK_MODEL,
            "query": TEST_QUERY,
            "documents": ["Revenue in the Southeast grew 31% YoY driven by retail expansion."],
        }
        try:
            async with httpx.AsyncClient(
                base_url=EMBED_BASE_URL,
                headers=_raw_headers(),
                timeout=10.0,
            ) as client:
                r = await client.post("/rerank", json=payload)
                ms = (time.monotonic() - t0) * 1000
                r.raise_for_status()
                body = r.json()
                results = body.get("results", [])
                print(f"  F1 Reranker: OK | {_fmt_ms(ms)} | results={len(results)}")
        except Exception as exc:
            ms = (time.monotonic() - t0) * 1000
            print(f"  F1 Reranker: FAIL | {_fmt_ms(ms)} | {type(exc).__name__}: {exc}")

    # F2: OpenRouter key info
    print("\n  F2: OpenRouter /auth/key (usage/limits -- no secret values printed)")
    try:
        async with httpx.AsyncClient(
            base_url=EMBED_BASE_URL,
            headers=_raw_headers(),
            timeout=8.0,
        ) as client:
            r = await client.get("/auth/key")
            body = r.json()
        data = body.get("data", {})
        safe_fields = {
            k: v for k, v in data.items()
            if k not in ("key", "token", "hash", "id") and not isinstance(v, dict)
        }
        print(f"  Key info: {safe_fields}")
        rate_limit = data.get("rate_limit", {})
        if rate_limit:
            print(f"  Rate limits: {rate_limit}")
    except Exception as exc:
        print(f"  F2 key info: FAIL | {exc} (skip if endpoint unavailable)")

    # F3: Model status
    print(f"\n  F3: Model endpoint status for {EMBED_MODEL}")
    try:
        async with httpx.AsyncClient(
            base_url=EMBED_BASE_URL,
            headers=_raw_headers(),
            timeout=8.0,
        ) as client:
            model_id_enc = EMBED_MODEL.replace("/", "%2F").replace(":", "%3A")
            r = await client.get(f"/models/{model_id_enc}")
            if r.status_code == 200:
                body = r.json()
                data = body.get("data", body)
                safe = {
                    k: v for k, v in (data.items() if isinstance(data, dict) else {}.items())
                    if k in ("id", "name", "context_length", "top_provider", "per_request_limits",
                             "description", "architecture", "pricing", "created")
                }
                print(f"  Model info: {safe}")
            else:
                print(f"  Model endpoint returned {r.status_code} -- skip")
    except Exception as exc:
        print(f"  F3 model info: FAIL | {exc} (skip)")


# Results table & verdict

def print_verdict(a_rows: List[Dict], b_rows: List[Dict]) -> str:
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    a_ok   = [r for r in a_rows if r.get("ok")]
    a_fail = [r for r in a_rows if not r.get("ok")]
    b_ok   = [r for r in b_rows if r.get("ok")]
    b_fail = [r for r in b_rows if not r.get("ok")]

    a_times = [r["ms"] for r in a_rows if r.get("ok")]
    b_times = [r["ms"] for r in b_rows if r.get("ok")]

    print(f"\n  Test A (raw)  : {len(a_ok)}/{len(a_rows)} ok  "
          f"| avg ok latency = {_fmt_ms(sum(a_times)/max(len(a_times),1))}"
          f"  | {len(a_fail)} fail")
    print(f"  Test B (app)  : {len(b_ok)}/{len(b_rows)} ok  "
          f"| avg ok latency = {_fmt_ms(sum(b_times)/max(len(b_times),1))}"
          f"  | {len(b_fail)} fail")

    a_slow  = sum(1 for r in a_rows if r.get("ms", 0) > 3000)
    a_bad   = len(a_fail) + a_slow

    print(f"\n  A calls >3 s or failing: {a_bad}/{len(a_rows)}")

    if a_bad > len(a_rows) / 2:
        verdict = "PROVIDER"
        reason  = (f"{a_bad}/{len(a_rows)} raw calls (Test A) failed or exceeded 3 s; "
                   "the problem is on the provider side.")
    elif b_fail and not a_fail:
        verdict = "OUR REQUEST"
        reason  = ("Raw calls (A) succeeded but app-path calls (B) failed; "
                   "likely a request body or client configuration difference.")
    elif a_fail and a_slow == 0 and len(a_fail) > 0:
        verdict = "PROVIDER"
        reason  = "All raw requests failed (network / auth / provider error)."
    else:
        verdict = "MIXED/UNCLEAR"
        reason  = ("Both A and B show some failures but the pattern is ambiguous. "
                   "Check the idle-gap test (E) and concurrency test (D) output above.")

    print(f"\n  VERDICT: {verdict}")
    print(f"  REASON : {reason}")
    print()
    return verdict


# Main

async def main() -> None:
    print_config()

    a_rows = await test_a()
    b_rows = await test_b()
    await diff_a_vs_b()
    await test_c()
    await test_d()
    await test_e()
    await test_f()

    verdict = print_verdict(a_rows, b_rows)
    print(f"\nTotal requests used: {TOTAL_REQUEST_COUNT} / {MAX_REQUESTS}")
    print(f"Final verdict: {verdict}")


if __name__ == "__main__":
    asyncio.run(main())
