"""
backend/scripts/verify_data_state.py
Read-only script to verify the current state of real data stores,
repo hygiene, test isolation fixtures, and backups.
Does NOT write, delete, or modify any database, file under data/, or Redis key.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

# Paths & Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "rag.db"
CHROMA_PATH = DATA_DIR / "chroma_db"
UPLOADS_DIR = DATA_DIR / "uploads"
ADE_OUT_DIR = DATA_DIR / "ade_outputs"
TELEMETRY_PATH = DATA_DIR / "telemetry.jsonl"
TESTS_DIR = BACKEND_DIR / "tests"
ENV_PATH = BACKEND_DIR / ".env"

EXPECTED_DOC_NAMES = [
    "Agentic_AI_Coding_Interview_Questions_and_Answers.docx",
    "5_long_annual_report.pdf",
    "1_text_policy_memo.docx",
]
EXPECTED_USERNAMES = ["test", "test2"]
EXPECTED_CHROMA_TOTAL = 103
EXPECTED_CHROMA_BREAKDOWN = {88, 8, 7}


def header(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def check_sqlite():
    header("CHECK 1: SQLite (data/rag.db)")
    if not DB_PATH.exists():
        print(f"[FAIL] SQLite database not found at {DB_PATH}")
        return False, {}, {}, {}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Users
    cursor.execute("SELECT user_id, username, created_at FROM users")
    users = cursor.fetchall()
    user_map = {u["username"]: u["user_id"] for u in users}
    user_ids = {u["user_id"]: u["username"] for u in users}

    print(f"Total Users: {len(users)}")
    for u in users:
        is_expected = u["username"] in EXPECTED_USERNAMES
        flag = "" if is_expected else " [UNEXPECTED]"
        print(f"  - user_id: {u['user_id']} | username: {u['username']} | created_at: {u['created_at']}{flag}")

    users_pass = len(users) == 2 and set(user_map.keys()) == set(EXPECTED_USERNAMES)
    extra_users = [u["username"] for u in users if u["username"] not in EXPECTED_USERNAMES]
    if extra_users:
        print(f"  -> Unexpected Users ({len(extra_users)}): {extra_users}")
    print(f"  -> Users Check: {'PASS' if users_pass else 'FAIL'} (expected exactly {EXPECTED_USERNAMES}, found {len(users)} users)")

    # Documents
    cursor.execute("SELECT document_id, user_id, filename, chunk_count, status, created_at FROM documents")
    docs = cursor.fetchall()
    doc_map = {d["document_id"]: dict(d) for d in docs}
    doc_filenames = [d["filename"] for d in docs]

    print(f"\nTotal Documents: {len(docs)}")
    for d in docs:
        uname = user_ids.get(d["user_id"], f"UNKNOWN({d['user_id']})")
        is_expected = d["filename"] in EXPECTED_DOC_NAMES
        flag = "" if is_expected else " [UNEXPECTED]"
        print(f"  - doc_id: {d['document_id']}")
        print(f"    filename: {d['filename']} | user: {uname} | chunk_count: {d['chunk_count']} | status: {d['status']}{flag}")

    docs_pass = len(docs) == 3 and set(doc_filenames) == set(EXPECTED_DOC_NAMES)
    extra_docs = [d["filename"] for d in docs if d["filename"] not in EXPECTED_DOC_NAMES]
    if extra_docs:
        print(f"  -> Unexpected Documents ({len(extra_docs)}): {extra_docs}")
    print(f"  -> Documents Check: {'PASS' if docs_pass else 'FAIL'} (expected exactly 3 documents, found {len(docs)})")

    # Jobs
    cursor.execute("SELECT job_id, user_id, document_id, status, error_message, created_at FROM jobs")
    jobs = cursor.fetchall()

    print(f"\nTotal Jobs: {len(jobs)}")
    for j in jobs:
        uname = user_ids.get(j["user_id"], f"UNKNOWN({j['user_id']})")
        doc_info = doc_map.get(j["document_id"], {}).get("filename", "UNKNOWN_DOC")
        print(f"  - job_id: {j['job_id']} | doc: {doc_info} ({j['document_id']}) | user: {uname} | status: {j['status']} | error: {j['error_message']}")

    jobs_pass = len(jobs) == 3
    if not jobs_pass:
        print(f"  -> Unexpected Jobs Count: found {len(jobs)}, expected 3")
    print(f"  -> Jobs Check: {'PASS' if jobs_pass else 'FAIL'} (expected exactly 3 jobs, found {len(jobs)})")

    overall = users_pass and docs_pass and jobs_pass
    print(f"\nSQLite Overall: {'PASS' if overall else 'FAIL'}")
    conn.close()
    return overall, user_map, user_ids, doc_map


def check_chromadb(real_doc_map: dict):
    header("CHECK 2: ChromaDB (data/chroma_db)")
    import chromadb

    if not CHROMA_PATH.exists():
        print(f"[FAIL] ChromaDB path not found at {CHROMA_PATH}")
        return False, {}

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        coll = client.get_collection("ade_documents")
    except Exception as e:
        print(f"[FAIL] Could not get collection 'ade_documents': {e}")
        return False, {}

    total_chunks = coll.count()
    print(f"Collection 'ade_documents' chunk count: {total_chunks}")

    data = coll.get(include=["metadatas"])
    metadatas = data.get("metadatas", [])

    chunk_counts_by_doc: dict[str, int] = {}
    for meta in metadatas:
        doc_id = meta.get("document_id", "UNKNOWN_DOC")
        chunk_counts_by_doc[doc_id] = chunk_counts_by_doc.get(doc_id, 0) + 1

    real_expected_docs = {
        did: dinfo for did, dinfo in real_doc_map.items()
        if dinfo.get("filename") in EXPECTED_DOC_NAMES
    }
    real_expected_ids = set(real_expected_docs.keys())
    orphan_doc_ids = set(chunk_counts_by_doc.keys()) - real_expected_ids

    print("\nChunk counts per document:")
    for doc_id, count in sorted(chunk_counts_by_doc.items(), key=lambda x: x[1], reverse=True):
        fname = real_doc_map.get(doc_id, {}).get("filename", "ORPHAN / UNKNOWN")
        is_expected = doc_id in real_expected_ids
        flag = "" if is_expected else " [ORPHAN/EXTRA]"
        print(f"  - doc_id: {doc_id} | count: {count} | file: {fname}{flag}")

    if orphan_doc_ids:
        print(f"\n[ALERT] Orphan / Non-expected document IDs in ChromaDB ({len(orphan_doc_ids)}): {orphan_doc_ids}")
    else:
        print("\nOrphan document IDs in ChromaDB: None (all chunks belong to the 3 real documents)")

    counts_set = set(chunk_counts_by_doc.values())
    total_pass = total_chunks == EXPECTED_CHROMA_TOTAL
    breakdown_pass = (counts_set == EXPECTED_CHROMA_BREAKDOWN) if not orphan_doc_ids else False
    no_orphans = len(orphan_doc_ids) == 0

    print(f"\nChromaDB Total Count check: {'PASS' if total_pass else 'FAIL'} (got {total_chunks}, expected {EXPECTED_CHROMA_TOTAL})")
    print(f"ChromaDB Breakdown check: {'PASS' if breakdown_pass else 'FAIL'} (counts: {counts_set}, expected {EXPECTED_CHROMA_BREAKDOWN})")
    print(f"ChromaDB Orphan check: {'PASS' if no_orphans else 'FAIL'}")

    overall = total_pass and breakdown_pass and no_orphans
    print(f"ChromaDB Overall: {'PASS' if overall else 'FAIL'}")
    return overall, chunk_counts_by_doc


def check_storage_folders(real_doc_map: dict):
    header("CHECK 3: Storage Folders (data/uploads & data/ade_outputs)")
    real_expected_docs = {
        did: dinfo for did, dinfo in real_doc_map.items()
        if dinfo.get("filename") in EXPECTED_DOC_NAMES
    }
    expected_ids = set(real_expected_docs.keys())

    # uploads
    upload_folders = [f.name for f in UPLOADS_DIR.iterdir() if f.is_dir()] if UPLOADS_DIR.exists() else []
    print(f"Upload folders ({len(upload_folders)}):")
    for f in upload_folders:
        fname = real_doc_map.get(f, {}).get("filename", "ORPHAN / UNKNOWN")
        flag = "" if f in expected_ids else " [EXTRA]"
        print(f"  - {f} ({fname}){flag}")

    upload_extras = set(upload_folders) - expected_ids
    upload_missing = expected_ids - set(upload_folders)
    upload_pass = len(upload_folders) == 3 and not upload_extras and not upload_missing

    print(f"  -> Extras: {list(upload_extras) if upload_extras else 'None'}")
    print(f"  -> Missing: {list(upload_missing) if upload_missing else 'None'}")
    print(f"  -> Uploads folders check: {'PASS' if upload_pass else 'FAIL'}")

    # ade_outputs
    ade_folders = [f.name for f in ADE_OUT_DIR.iterdir() if f.is_dir()] if ADE_OUT_DIR.exists() else []
    print(f"\nADE output folders ({len(ade_folders)}):")
    for f in ade_folders:
        fname = real_doc_map.get(f, {}).get("filename", "ORPHAN / UNKNOWN")
        flag = "" if f in expected_ids else " [EXTRA]"
        print(f"  - {f} ({fname}){flag}")

    pipeline_test_folders = [f for f in ade_folders if f.startswith("pipeline_test_doc_")]
    ade_extras = set(ade_folders) - expected_ids
    ade_missing = expected_ids - set(ade_folders)
    ade_pass = len(ade_folders) == 3 and not ade_extras and not ade_missing and len(pipeline_test_folders) == 0

    print(f"  -> Pipeline test folders: {pipeline_test_folders if pipeline_test_folders else 'None'}")
    print(f"  -> Extras: {list(ade_extras) if ade_extras else 'None'}")
    print(f"  -> Missing: {list(ade_missing) if ade_missing else 'None'}")
    print(f"  -> ADE outputs folders check: {'PASS' if ade_pass else 'FAIL'}")

    overall = upload_pass and ade_pass
    print(f"Storage Folders Overall: {'PASS' if overall else 'FAIL'}")
    return overall


def check_consistency(real_doc_map: dict, chroma_counts: dict):
    header("CHECK 4: Consistency Across Stores")
    real_expected_docs = {
        did: dinfo for did, dinfo in real_doc_map.items()
        if dinfo.get("filename") in EXPECTED_DOC_NAMES
    }

    all_consistent = True

    print(f"Checking consistency for the 3 real documents:")
    for doc_id, doc in real_expected_docs.items():
        fname = doc["filename"]
        sql_chunks = doc["chunk_count"]
        chroma_chunks = chroma_counts.get(doc_id, 0)
        has_upload = (UPLOADS_DIR / doc_id).is_dir()
        has_ade = (ADE_OUT_DIR / doc_id).is_dir()

        chunk_match = sql_chunks == chroma_chunks
        folders_match = has_upload and has_ade

        print(f"Document: {fname} ({doc_id})")
        print(f"  - SQLite chunks: {sql_chunks} | Chroma chunks: {chroma_chunks} -> {'MATCH' if chunk_match else 'MISMATCH'}")
        print(f"  - Upload folder exists: {has_upload} | ADE folder exists: {has_ade} -> {'MATCH' if folders_match else 'MISSING'}")

        if not (chunk_match and folders_match):
            all_consistent = False

    print(f"\nConsistency Overall: {'PASS' if all_consistent else 'FAIL'}")
    return all_consistent


def check_telemetry(user_ids_by_id: dict):
    header("CHECK 5: Telemetry (data/telemetry.jsonl)")
    if not TELEMETRY_PATH.exists():
        print(f"[FAIL] Telemetry file not found at {TELEMETRY_PATH}")
        return False

    records = []
    with open(TELEMETRY_PATH, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append((idx, rec))
            except Exception as e:
                print(f"Malformed JSON at line {idx}: {e}")

    print(f"Total Telemetry Records: {len(records)}")

    by_type: dict[str, int] = {}
    by_user: dict[str, int] = {}
    flagged = []

    valid_expected_user_ids = {
        uid for uid, uname in user_ids_by_id.items() if uname in EXPECTED_USERNAMES
    }

    for line_no, r in records:
        rtype = r.get("record_type", "unknown")
        uid = r.get("user_id")

        by_type[rtype] = by_type.get(rtype, 0) + 1
        uid_str = str(uid) if uid is not None else "NONE"
        by_user[uid_str] = by_user.get(uid_str, 0) + 1

        is_flagged = False
        reasons = []

        if uid is None or uid == "":
            is_flagged = True
            reasons.append("missing_user_id")
        elif uid in ("test_user", "test_user_001"):
            is_flagged = True
            reasons.append(f"synthetic_user_id_{uid}")
        elif uid not in valid_expected_user_ids:
            uname = user_ids_by_id.get(uid, "NOT_IN_USERS_TABLE")
            is_flagged = True
            reasons.append(f"non_expected_user({uname})")

        q_text = r.get("question_text", "") or ""
        if "What is the total revenue?" in q_text:
            is_flagged = True
            reasons.append("revenue_test_query")

        if is_flagged:
            flagged.append((line_no, reasons, r))

    print("\nBreakdown by record_type:")
    for t, count in sorted(by_type.items()):
        print(f"  - {t}: {count}")

    print("\nBreakdown by user_id:")
    for u, count in sorted(by_user.items()):
        uname = user_ids_by_id.get(u, "NOT_IN_USERS_TABLE")
        flag = "" if u in valid_expected_user_ids else " [UNEXPECTED]"
        print(f"  - {u} ({uname}): {count}{flag}")

    print(f"\nTotal Flagged Records: {len(flagged)}")
    if flagged:
        print("First 5 flagged records:")
        for line_no, reasons, r in flagged[:5]:
            q_info = f" | question: '{r.get('question_text')}'" if 'question_text' in r else ""
            print(f"  [Line {line_no}] Reasons: {reasons} | Type: {r.get('record_type')} | User: {r.get('user_id')}{q_info}")
    else:
        print("  None. All records belong to real users with no synthetic test questions.")

    overall = len(flagged) == 0
    print(f"\nTelemetry Overall: {'PASS' if overall else 'FAIL'}")
    return overall


async def check_redis(user_ids_by_id: dict):
    header("CHECK 6: Redis (READ-ONLY Scan)")
    import redis.asyncio as aioredis
    from app.core.config import get_settings

    settings = get_settings()
    redis_url = settings.REDIS_URL

    if not redis_url:
        print("[FAIL] REDIS_URL not configured")
        return False

    client = aioredis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )

    try:
        pong = await client.ping()
    except Exception as e:
        print(f"[FAIL] Redis ping failed: {type(e).__name__}: {e}")
        return False

    keys = []
    cursor = 0
    while True:
        cursor, batch = await client.scan(cursor=cursor, count=100)
        keys.extend(batch)
        if cursor == 0:
            break

    await client.aclose()

    print(f"Total Redis Keys Found: {len(keys)}")
    print("Scanned key names:")

    valid_expected_user_ids = {
        uid for uid, uname in user_ids_by_id.items() if uname in EXPECTED_USERNAMES
    }
    flagged_keys = []

    for k in sorted(keys):
        is_known = False
        if k.startswith("embed_cache:"):
            is_known = True
            print(f"  - {k} [embed_cache key]")
        elif k.startswith("user:"):
            parts = k.split(":")
            if len(parts) >= 2 and parts[1] in valid_expected_user_ids:
                uname = user_ids_by_id.get(parts[1])
                is_known = True
                print(f"  - {k} [real user: {uname}]")
            elif len(parts) >= 2 and parts[1] in ("test_user", "test_user_001"):
                print(f"  - {k} [FLAGGED: synthetic user]")
                flagged_keys.append((k, f"belongs to synthetic user {parts[1]}"))
                continue
            else:
                uname = user_ids_by_id.get(parts[1], "unknown")
                print(f"  - {k} [FLAGGED: user {uname} not test/test2]")
                flagged_keys.append((k, f"user key does not belong to test/test2 (user: {uname})"))
                continue
        elif k in ("test_key",):
            is_known = True
            print(f"  - {k} [known test key]")

        if not is_known:
            print(f"  - {k} [FLAGGED: unknown pattern]")
            flagged_keys.append((k, "unknown key pattern"))

    print(f"\nFlagged Keys: {len(flagged_keys)}")
    if flagged_keys:
        for k, reason in flagged_keys:
            print(f"  - {k} -> {reason}")
    else:
        print("  None. All keys are known app keys or belong to the 2 real users.")

    overall = len(flagged_keys) == 0
    print(f"Redis Overall: {'PASS' if overall else 'FAIL'}")
    return overall


def check_test_isolation():
    header("CHECK 7: Test Isolation & conftest.py Safety Guard")
    conftest_path = TESTS_DIR / "conftest.py"
    if not conftest_path.exists():
        print(f"[FAIL] conftest.py not found at {conftest_path}")
        return False

    conftest_content = conftest_path.read_text(encoding="utf-8")
    has_guard = "_run_safety_guard" in conftest_content
    has_sessionstart = "def pytest_sessionstart" in conftest_content
    has_sessionfinish = "def pytest_sessionfinish" in conftest_content
    has_test_env = "def set_test_env" in conftest_content

    print(f"conftest.py checks:")
    print(f"  - _run_safety_guard present: {has_guard}")
    print(f"  - pytest_sessionstart hook present: {has_sessionstart}")
    print(f"  - pytest_sessionfinish hook present: {has_sessionfinish}")
    print(f"  - set_test_env fixture present: {has_test_env}")

    hardcoded_hits = []
    pattern = re.compile(r'["\'](?:\./)?data/[^"\']*["\']')

    for py_file in TESTS_DIR.rglob("*.py"):
        if py_file.name == "conftest.py":
            continue
        for line in py_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line_str = line.strip()
            if line_str.startswith("#") or line_str.startswith('"""') or line_str.startswith("'''"):
                continue
            if "assert not" in line_str and "exists()" in line_str:
                continue
            matches = pattern.findall(line)
            if matches:
                hardcoded_hits.append((py_file.name, matches))

    print(f"\nHardcoded 'data/' write paths in test files (excluding conftest.py):")
    if hardcoded_hits:
        for fname, m in hardcoded_hits:
            print(f"  - {fname}: {m}")
    else:
        print("  None. No test file hardcodes writes to real data/.")

    fixtures_ok = has_guard and has_sessionstart and has_sessionfinish and has_test_env
    overall = fixtures_ok and len(hardcoded_hits) == 0
    print(f"Test Isolation Overall: {'PASS' if overall else 'FAIL'}")
    return overall


def check_repo_hygiene():
    header("CHECK 8: Repo Hygiene (git status, check-ignore, tracked files)")
    # 1. git status --short
    res_status = subprocess.run(["git", "status", "--short"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    status_out = res_status.stdout.strip()
    print("git status --short:")
    for line in status_out.splitlines():
        print(f"  {line}")

    # 2. git check-ignore -v backend/data backend/.env *.bak
    targets = ["backend/data", "backend/.env", "test.bak"]
    res_ignore = subprocess.run(["git", "check-ignore", "-v"] + targets, cwd=str(REPO_ROOT), capture_output=True, text=True)
    ignore_out = res_ignore.stdout.strip()
    print("\ngit check-ignore -v on targets:")
    if ignore_out:
        for line in ignore_out.splitlines():
            print(f"  {line}")
    else:
        print("  (No output - none ignored)")

    # 3. git ls-files backend/data
    res_ls = subprocess.run(["git", "ls-files", "backend/data"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    ls_out = res_ls.stdout.strip()
    print("\ngit ls-files backend/data (tracked files in backend/data):")
    tracked_files = ls_out.splitlines() if ls_out else []
    if tracked_files:
        for f in tracked_files:
            print(f"  - {f}")
    else:
        print("  None. No files under backend/data are tracked by git.")

    overall = len(tracked_files) == 0
    print(f"Repo Hygiene Overall: {'PASS' if overall else 'FAIL'}")
    return overall


def check_backups():
    header("CHECK 9: Existing *.bak Files/Folders Across Repo")
    bak_items = []
    for root, dirs, files in os.walk(REPO_ROOT):
        if ".git" in root:
            continue
        for d in dirs:
            if d.endswith(".bak"):
                bak_items.append(os.path.join(root, d) + "/")
        for f in files:
            if f.endswith(".bak"):
                bak_items.append(os.path.join(root, f))

    print(f"Total *.bak items found: {len(bak_items)}")
    if bak_items:
        for b in sorted(bak_items):
            rel = os.path.relpath(b, REPO_ROOT)
            print(f"  - {rel}")
    else:
        print("  None. No *.bak files or directories exist anywhere in the repository.")
    overall = len(bak_items) == 0
    print(f"Backups Overall: {'PASS' if overall else 'FAIL'}")
    return overall, bak_items


async def main():
    print("=" * 70)
    print(" REAL DATA STORES READ-ONLY VERIFICATION")
    print("=" * 70)

    # 1. SQLite
    sql_ok, user_map, user_ids_by_id, doc_map = check_sqlite()

    # 2. ChromaDB
    chroma_ok, chroma_counts = check_chromadb(doc_map)

    # 3. Storage Folders
    storage_ok = check_storage_folders(doc_map)

    # 4. Consistency
    consistency_ok = check_consistency(doc_map, chroma_counts)

    # 5. Telemetry
    telemetry_ok = check_telemetry(user_ids_by_id)

    # 6. Redis
    redis_ok = await check_redis(user_ids_by_id)

    # 7. Test Isolation
    isolation_ok = check_test_isolation()

    # 8. Repo Hygiene
    hygiene_ok = check_repo_hygiene()

    # 9. Backups
    backups_ok, bak_items = check_backups()

    header("VERIFICATION SUMMARY TABLE")
    summary = [
        ("1. SQLite (data/rag.db users/docs/jobs)", sql_ok),
        ("2. ChromaDB (ade_documents 103 chunks)", chroma_ok),
        ("3. Storage Folders (uploads & ade_outputs)", storage_ok),
        ("4. Consistency Across Stores", consistency_ok),
        ("5. Telemetry (data/telemetry.jsonl)", telemetry_ok),
        ("6. Redis (Read-Only Scan)", redis_ok),
        ("7. Test Isolation & Safety Guard", isolation_ok),
        ("8. Repo Hygiene (git status & tracking)", hygiene_ok),
        ("9. Backups Cleaned (*.bak items)", backups_ok),
    ]

    for name, status in summary:
        print(f"  [{'PASS' if status else 'FAIL'}] {name}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
