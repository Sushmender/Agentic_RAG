"""
backend/scripts/try_rewrite.py
Manual smoke-test for the follow-up query rewriter.

NOT part of the automated test suite.
Calls the real Groq API. Run from backend/ with .venv activated:

    python scripts/try_rewrite.py

Prints: history, original query, standalone result, decision, applied, and rewrite_ms for each example.
"""
from __future__ import annotations

import asyncio
import sys
import os

# Allow running from backend/ directory without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so settings picks up GROQ_API_KEY etc. (never printed)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass  # python-dotenv optional — rely on env vars already set


from app.services.query_rewriter import rewrite_query  # noqa: E402

SAMPLE_HISTORY = [
    {"role": "user", "content": "What was the customer retention rate this year?"},
    {"role": "assistant", "content": "Customer retention was 92% this year, compared to 88% last year."},
]

POLICY_HISTORY = [
    {"role": "user", "content": "Who needs to approve an exception to the remote work policy?"},
    {"role": "assistant", "content": "Both the employee's direct manager and the department head must approve exceptions."},
]

GROWTH_HISTORY = [
    {"role": "user", "content": "How did Southeast growth compare to Northeast?"},
    {"role": "assistant", "content": "Southeast grew 31% while Northeast grew 9% due to local competition."},
]

CONTRACTOR_HISTORY = [
    {"role": "user", "content": "Does this policy apply to contractors?"},
    {"role": "assistant", "content": "The remote work policy applies only to full-time employees, not contractors."},
]

EXAMPLES = [
    # ── 10 Standalone Examples (history present) ──────────────────────────────
    {
        "name": "Standalone 1: retention rate",
        "history": SAMPLE_HISTORY,
        "query": "What was the customer retention rate this year?",
    },
    {
        "name": "Standalone 2: VP-level roles",
        "history": SAMPLE_HISTORY,
        "query": "Which VP-level roles were hired in Q3?",
    },
    {
        "name": "Standalone 3: policy contractors",
        "history": POLICY_HISTORY,
        "query": "Does this policy apply to contractors?",
    },
    {
        "name": "Standalone 4: remote work approval",
        "history": POLICY_HISTORY,
        "query": "Who needs to approve an exception to the remote work policy?",
    },
    {
        "name": "Standalone 5: conclusions",
        "history": POLICY_HISTORY,
        "query": "What are the conclusions?",
    },
    {
        "name": "Standalone 6: days per week",
        "history": POLICY_HISTORY,
        "query": "How many days per week can employees work remotely?",
    },
    {
        "name": "Standalone 7: key findings",
        "history": SAMPLE_HISTORY,
        "query": "Summarize the key findings",
    },
    {
        "name": "Standalone 8: main topics",
        "history": SAMPLE_HISTORY,
        "query": "What are the main topics covered?",
    },
    {
        "name": "Standalone 9: tables or charts",
        "history": SAMPLE_HISTORY,
        "query": "Show me any tables or charts",
    },
    {
        "name": "Standalone 10: total revenue",
        "history": SAMPLE_HISTORY,
        "query": "What is the total revenue?",
    },

    # ── 4 Follow-up Examples ──────────────────────────────────────────────────
    {
        "name": "Follow-up 1: and what drove it?",
        "history": GROWTH_HISTORY,
        "query": "and what drove it?",
    },
    {
        "name": "Follow-up 2: full-time members",
        "history": CONTRACTOR_HISTORY,
        "query": "Then what about full-time members?",
    },
    {
        "name": "Follow-up 3: retention rate change",
        "history": SAMPLE_HISTORY,
        "query": "How did it change?",
    },
    {
        "name": "Follow-up 4: what about Northeast",
        "history": GROWTH_HISTORY,
        "query": "what about the Northeast?",
    },
]


async def main() -> None:
    print("=" * 70)
    print("  Follow-up Query Rewriter — Verification Run")
    print("=" * 70)

    for i, ex in enumerate(EXAMPLES, 1):
        print(f"\n[{i}/{len(EXAMPLES)}] {ex['name']}")
        print(f"  Query      : {ex['query']}")

        result = await rewrite_query(query=ex["query"], history=ex["history"])

        print(f"  Decision   : {result.rewrite_decision}")
        print(f"  Applied    : {result.applied}")
        print(f"  Method     : {result.rewrite_method}")
        print(f"  Standalone : {result.standalone_query}")
        print(f"  Latency    : {result.rewrite_ms:.1f} ms")
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
