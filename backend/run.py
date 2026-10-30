"""
backend/run.py
Launcher script for the backend API.
Defaults host to 127.0.0.1 (local loopback), configurable via HOST environment variable.
Defaults port to 8000, configurable via PORT environment variable.
"""
from __future__ import annotations

import argparse
import os
import uuid
import uvicorn

if __name__ == "__main__":
    if "APP_BOOT_ID" not in os.environ:
        os.environ["APP_BOOT_ID"] = str(uuid.uuid4())

    parser = argparse.ArgumentParser(description="Launcher script for the backend API.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Bind host")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Bind port")
    parser.add_argument("--reload", action="store_true", default=os.getenv("RELOAD", "true").lower() in ("true", "1", "yes"), help="Enable auto-reload")
    args, _ = parser.parse_known_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)
