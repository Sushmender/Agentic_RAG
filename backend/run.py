"""
backend/run.py
Launcher script for the backend API.
Defaults host to 127.0.0.1 (local loopback), configurable via HOST environment variable.
Defaults port to 8000, configurable via PORT environment variable.
"""
from __future__ import annotations

import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
