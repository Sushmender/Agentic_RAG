"""
backend/scripts/try_rewrite.py
Manual smoke-test for the follow-up query rewriter.

NOT part of the automated test suite.
Calls the real Groq API. Run from backend/ with .venv activated:

    python scripts/try_rewrite.py

Prints: history, original query, standalone result, and rewrite_ms for each example.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from backend/ directory without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so settings picks up GROQ_API_KEY etc.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass  # python-dotenv optional — rely on env vars already set


from app.services.query_rewriter import rewrite_query  # noqa: E402


EXAMPLES = [
    {
        "name": "Follow-up: full-time members",
        "history": [
            {"role": "user", "content": "Does this policy apply to contractors?"},
            {"role": "assistant", "content": "The policy primarily covers contractors working on fixed-term engagements."},
        ],
        "query": "Then what about full-time members?",
    },
    {
        "name": "Follow-up: what drove growth",
        "history": [
            {"role": "user", "content": "How did Southeast growth compare to Northeast?"},
            {"role": "assistant", "content": "Southeast grew 12% YoY vs. 4% for the Northeast."},
        ],
        "query": "and what drove it?",
    },
    {
        "name": "Follow-up: retention rate change",
        "history": [
            {"role": "user", "content": "What was the retention rate?"},
            {"role": "assistant", "content": "The retention rate was 87% in 2023."},
        ],
        "query": "How did it change?",
    },
    {
        "name": "Already standalone (with history)",
        "history": [
            {"role": "user", "content": "What was the retention rate?"},
            {"role": "assistant", "content": "The retention rate was 87% in 2023."},
        ],
        "query": "What was the employee turnover rate in the last fiscal year?",
    },
    {
        "name": "No history (standalone, no call expected)",
        "history": None,
        "query": "What are the key findings in the executive summary?",
    },
]


async def main() -> None:
    print("=" * 70)
    print("  Follow-up Query Rewriter — Real-World Check")
    print("=" * 70)

    for i, ex in enumerate(EXAMPLES, 1):
        print(f"\n[{i}/{len(EXAMPLES)}] {ex['name']}")
        print(f"  History : {ex['history']}")
        print(f"  Original: {ex['query']}")

        result = await rewrite_query(query=ex["query"], history=ex["history"])

        print(f"  Standalone : {result.standalone_query}")
        print(f"  Applied    : {result.applied}")
        print(f"  rewrite_ms : {result.rewrite_ms:.1f} ms")
        if result._raw_output:
            print(f"  Raw output : {result._raw_output!r}")
        if result._rejection_reason:
            print(f"  Rejection  : {result._rejection_reason}")
        if result.applied:
            print(f"  Tokens     : in={result.input_tokens} out={result.output_tokens} "
                  f"total={result.total_tokens}  cost=${result.cost_usd:.6f}")

    print("\n" + "=" * 70)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
