"""
backend/app/api/v1/router.py
Main API v1 router — aggregates all endpoint routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, documents, evaluation, health, jobs, metrics, query

api_router = APIRouter(prefix="/api/v1")

# Health (no auth)
api_router.include_router(health.router)

# Auth (no auth required for register/login)
api_router.include_router(auth.router)

# Protected routes (require JWT)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(query.router)

# Observability (no auth — Day 7 + Day 8)
api_router.include_router(metrics.router)
api_router.include_router(evaluation.router)
