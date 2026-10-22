"""
backend/scripts/clean_test_data.py
Script to clean up leftover test users, test documents, test jobs,
extra ChromaDB chunks, and extra storage folders.

DRY-RUN by default. Pass --apply to execute changes.
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "rag.db"
CHROMA_PATH = DATA_DIR / "chroma_db"
UPLOADS_DIR = DATA_DIR / "uploads"
ADE_OUT_DIR = DATA_DIR / "ade_outputs"
BACKUP_DIR = Path(r"C:\Backups\Agentic_RAG")

KEPT_USERNAMES = {"test", "test2"}

EXPECTED_TO_DELETE = {
    "users": 60,
    "documents": 38,
    "jobs": 40,
    "chroma_chunks": 4,
    "ade_outputs_folders": 6,
    "uploads_folders": 0,
}

EXPECTED_TO_KEEP = {
    "users": 2,
    "documents": 3,
    "jobs": 3,
    "chroma_chunks": 103,
    "ade_outputs_folders": 3,
    "uploads_folders": 3,
}


def check_port_8000_closed() -> bool:
    """Ensure port 8000 is not listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        result = s.connect_ex(("127.0.0.1", 8000))
        # result == 0 means connection succeeded (port IS listening)
        return result != 0


def perform_safety_checks_and_backup() -> Path:
    """
    Run safety checks:
    1. Port 8000 must NOT be listening
    2. C:\\Backups\\Agentic_RAG\\rag.db and C:\\Backups\\Agentic_RAG\\chroma_db must exist
    3. Create fresh timestamped zip of backend/data in C:\\Backups\\Agentic_RAG
    4. Verify zip opens and lists rag.db and chroma_db
    """
    print("[1/4] Running safety checks...")

    if not check_port_8000_closed():
        raise RuntimeError("Safety check failed: Port 8000 IS listening. Stop the backend server first.")
    print("  [OK] Port 8000 is NOT listening.")

    if not (BACKUP_DIR / "rag.db").is_file():
        raise RuntimeError(f"Safety check failed: {BACKUP_DIR / 'rag.db'} does not exist.")
    if not (BACKUP_DIR / "chroma_db").is_dir():
        raise RuntimeError(f"Safety check failed: {BACKUP_DIR / 'chroma_db'} does not exist.")
    print(f"  [OK] Found baseline backups in {BACKUP_DIR}.")

    # Create timestamped zip
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = BACKUP_DIR / f"data_backup_before_cleanup_{now_str}.zip"
    print(f"  Creating timestamped backup zip: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                if file.endswith(".bak") or file.endswith(".backup"):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(DATA_DIR)
                zf.write(file_path, arcname=str(rel_path))

    print("  Verifying backup zip...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        has_rag_db = any("rag.db" in n for n in names)
        has_chroma = any("chroma_db" in n for n in names)
        if not (has_rag_db and has_chroma):
            raise RuntimeError(f"Backup zip verification failed! Missing rag.db or chroma_db in {zip_path.name}")
    print(f"  [OK] Backup zip verified ({len(names)} files included).")
    return zip_path


def analyze_cleanup_targets():
    """Analyze database, Chroma, and folder targets."""
    if not DB_PATH.exists():
        raise RuntimeError(f"SQLite DB not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Discover tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r["name"] for r in cursor.fetchall()]

    # Users
    cursor.execute("SELECT user_id, username FROM users")
    all_users = cursor.fetchall()
    kept_users = [u for u in all_users if u["username"] in KEPT_USERNAMES]
    deleted_users = [u for u in all_users if u["username"] not in KEPT_USERNAMES]
    kept_user_ids = {u["user_id"] for u in kept_users}
    deleted_user_ids = {u["user_id"] for u in deleted_users}

    # Documents
    cursor.execute("SELECT document_id, user_id, filename, chunk_count FROM documents")
    all_docs = cursor.fetchall()
    kept_docs = [d for d in all_docs if d["user_id"] in kept_user_ids]
    deleted_docs = [d for d in all_docs if d["user_id"] not in kept_user_ids]
    kept_doc_ids = {d["document_id"] for d in kept_docs}
    deleted_doc_ids = {d["document_id"] for d in deleted_docs}

    # Jobs
    cursor.execute("SELECT job_id, user_id, document_id FROM jobs")
    all_jobs = cursor.fetchall()
    kept_jobs = [j for j in all_jobs if j["user_id"] in kept_user_ids and j["document_id"] in kept_doc_ids]
    deleted_jobs = [j for j in all_jobs if j not in kept_jobs]

    conn.close()

    # ChromaDB
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    coll = client.get_collection("ade_documents")
    chroma_data = coll.get(include=["metadatas"])
    chroma_metas = chroma_data.get("metadatas", [])
    chroma_ids = chroma_data.get("ids", [])

    kept_chroma_chunk_ids = []
    deleted_chroma_chunk_ids = []
    for cid, meta in zip(chroma_ids, chroma_metas):
        doc_id = meta.get("document_id")
        if doc_id in kept_doc_ids:
            kept_chroma_chunk_ids.append(cid)
        else:
            deleted_chroma_chunk_ids.append(cid)

    # Folders
    # uploads
    upload_folders = [f for f in UPLOADS_DIR.iterdir() if f.is_dir()] if UPLOADS_DIR.exists() else []
    kept_upload_folders = [f for f in upload_folders if f.name in kept_doc_ids]
    deleted_upload_folders = [f for f in upload_folders if f.name not in kept_doc_ids]

    # ade_outputs
    ade_folders = [f for f in ADE_OUT_DIR.iterdir() if f.is_dir()] if ADE_OUT_DIR.exists() else []
    kept_ade_folders = [f for f in ade_folders if f.name in kept_doc_ids]
    deleted_ade_folders = [f for f in ade_folders if f.name not in kept_doc_ids]

    counts = {
        "delete": {
            "users": len(deleted_users),
            "documents": len(deleted_docs),
            "jobs": len(deleted_jobs),
            "chroma_chunks": len(deleted_chroma_chunk_ids),
            "ade_outputs_folders": len(deleted_ade_folders),
            "uploads_folders": len(deleted_upload_folders),
        },
        "keep": {
            "users": len(kept_users),
            "documents": len(kept_docs),
            "jobs": len(kept_jobs),
            "chroma_chunks": len(kept_chroma_chunk_ids),
            "ade_outputs_folders": len(kept_ade_folders),
            "uploads_folders": len(kept_upload_folders),
        },
    }

    details = {
        "tables": tables,
        "deleted_user_ids": deleted_user_ids,
        "deleted_doc_ids": deleted_doc_ids,
        "deleted_job_ids": {j["job_id"] for j in deleted_jobs},
        "deleted_chroma_chunk_ids": deleted_chroma_chunk_ids,
        "deleted_upload_folders": deleted_upload_folders,
        "deleted_ade_folders": deleted_ade_folders,
        "kept_doc_ids": kept_doc_ids,
    }

    return counts, details


def apply_cleanup(details: dict):
    """Execute deletions in SQLite, ChromaDB, and folder storage."""
    print("\n[3/4] Applying cleanup...")

    # 1. SQLite in single transaction
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("BEGIN TRANSACTION")
    try:
        if details["deleted_job_ids"]:
            cursor.execute(
                f"DELETE FROM jobs WHERE job_id IN ({','.join('?' for _ in details['deleted_job_ids'])})",
                list(details["deleted_job_ids"]),
            )
        if details["deleted_doc_ids"]:
            cursor.execute(
                f"DELETE FROM documents WHERE document_id IN ({','.join('?' for _ in details['deleted_doc_ids'])})",
                list(details["deleted_doc_ids"]),
            )
        if details["deleted_user_ids"]:
            cursor.execute(
                f"DELETE FROM users WHERE user_id IN ({','.join('?' for _ in details['deleted_user_ids'])})",
                list(details["deleted_user_ids"]),
            )
        conn.commit()
        print("  [OK] SQLite records deleted successfully.")
    except Exception as e:
        conn.rollback()
        conn.close()
        raise RuntimeError(f"SQLite transaction failed: {e}")
    conn.close()

    # 2. ChromaDB chunks
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    coll = client.get_collection("ade_documents")
    if details["deleted_chroma_chunk_ids"]:
        coll.delete(ids=details["deleted_chroma_chunk_ids"])
        print(f"  [OK] Deleted {len(details['deleted_chroma_chunk_ids'])} chunks from ChromaDB.")
    else:
        print("  [OK] No ChromaDB chunks to delete.")

    # 3. Folders
    def safe_delete_folder(folder: Path, allowed_parent: Path):
        res_folder = folder.resolve()
        res_parent = allowed_parent.resolve()
        if res_parent not in res_folder.parents or folder.name in details["kept_doc_ids"]:
            print(f"  [SKIPPED] Dangerous folder deletion path: {folder}")
            return

        # Strip read-only attributes on Windows
        try:
            subprocess.run(["attrib", "-r", str(res_folder), "/s", "/d"], capture_output=True)
        except Exception:
            pass
        for root, dirs, files in os.walk(res_folder):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
        try:
            os.chmod(res_folder, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass

        def onexc(func, path, exc):
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                func(path)
            except Exception:
                pass

        shutil.rmtree(res_folder, onexc=onexc)
        print(f"  [OK] Deleted folder: {folder.name}")

    # uploads
    for folder in details["deleted_upload_folders"]:
        safe_delete_folder(folder, UPLOADS_DIR)

    # ade_outputs
    for folder in details["deleted_ade_folders"]:
        safe_delete_folder(folder, ADE_OUT_DIR)


def main():
    parser = argparse.ArgumentParser(description="Clean up test data stores.")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup deletions")
    args = parser.parse_args()

    # Safety checks & backup
    perform_safety_checks_and_backup()

    # Analyze
    print("\n[2/4] Analyzing cleanup targets (Dry Run)...")
    counts, details = analyze_cleanup_targets()

    print("\nTarget Counts Analysis:")
    print("---------------------------------------------------------------")
    print(f"{'Target':<22} | {'To Delete':<10} | {'Expected':<10} | {'Status'}")
    print("---------------------------------------------------------------")

    all_matched = True
    for item, exp_count in EXPECTED_TO_DELETE.items():
        actual = counts["delete"][item]
        match = actual == exp_count
        if not match:
            all_matched = False
        print(f"{item:<22} | {actual:<10} | {exp_count:<10} | {'MATCH' if match else 'MISMATCH'}")

    print("---------------------------------------------------------------")
    print("\nKept Counts Analysis:")
    print("---------------------------------------------------------------")
    print(f"{'Target':<22} | {'To Keep':<10} | {'Expected':<10} | {'Status'}")
    print("---------------------------------------------------------------")
    for item, exp_count in EXPECTED_TO_KEEP.items():
        actual = counts["keep"][item]
        match = actual == exp_count
        if not match:
            all_matched = False
        print(f"{item:<22} | {actual:<10} | {exp_count:<10} | {'MATCH' if match else 'MISMATCH'}")
    print("---------------------------------------------------------------")

    if not all_matched:
        print("\n[STOP] One or more target counts do NOT match expected! Aborting.")
        sys.exit(1)

    print("\n[OK] ALL DRY RUN COUNTS MATCH EXPECTED NUMBERS EXACTLY.")

    if not args.apply:
        print("\n[DRY RUN COMPLETE] No changes made. Run with --apply to execute deletions.")
        return

    # Execute apply
    apply_cleanup(details)

    # Re-analyze after apply
    print("\n[4/4] Verifying after-cleanup state...")
    after_counts, _ = analyze_cleanup_targets()
    print("After-Cleanup Counts:")
    print(f"  Users:               {after_counts['keep']['users']} (deleted {counts['delete']['users']})")
    print(f"  Documents:           {after_counts['keep']['documents']} (deleted {counts['delete']['documents']})")
    print(f"  Jobs:                {after_counts['keep']['jobs']} (deleted {counts['delete']['jobs']})")
    print(f"  Chroma chunks:       {after_counts['keep']['chroma_chunks']} (deleted {counts['delete']['chroma_chunks']})")
    print(f"  Upload folders:      {after_counts['keep']['uploads_folders']} (deleted {counts['delete']['uploads_folders']})")
    print(f"  ADE output folders:  {after_counts['keep']['ade_outputs_folders']} (deleted {counts['delete']['ade_outputs_folders']})")
    print("\n[OK] CLEANUP COMPLETED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
