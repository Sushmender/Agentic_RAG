"""
backend/app/core/errors.py
Custom HTTP exception classes for the Multimodal RAG API.
All exceptions include a machine-readable error_code for client handling.
"""
from __future__ import annotations

from fastapi import HTTPException, status


class AppError(HTTPException):
    """Base application error with error_code."""

    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str, status_code: int = 500) -> None:
        super().__init__(status_code=status_code, detail=detail)


# ── 404 Not Found ──────────────────────────────────────────────────────────────
class DocumentNotFoundError(AppError):
    error_code = "DOCUMENT_NOT_FOUND"

    def __init__(self, document_id: str) -> None:
        super().__init__(
            detail=f"Document '{document_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class JobNotFoundError(AppError):
    error_code = "JOB_NOT_FOUND"

    def __init__(self, job_id: str) -> None:
        super().__init__(
            detail=f"Job '{job_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ChunkNotFoundError(AppError):
    error_code = "CHUNK_NOT_FOUND"

    def __init__(self, chunk_id: str) -> None:
        super().__init__(
            detail=f"Chunk '{chunk_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UserNotFoundError(AppError):
    error_code = "USER_NOT_FOUND"

    def __init__(self, user_id: str) -> None:
        super().__init__(
            detail=f"User '{user_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


# ── 400 Validation / Bad Request ───────────────────────────────────────────────
class FileTooLargeError(AppError):
    error_code = "FILE_TOO_LARGE"

    def __init__(self, size_mb: float, max_mb: int) -> None:
        super().__init__(
            detail=f"File size {size_mb:.1f} MB exceeds maximum {max_mb} MB.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class UnsupportedFileTypeError(AppError):
    error_code = "UNSUPPORTED_FILE_TYPE"

    def __init__(self, mime_type: str) -> None:
        super().__init__(
            detail=f"File type '{mime_type}' is not supported.",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class InvalidQueryError(AppError):
    error_code = "INVALID_QUERY"

    def __init__(self, detail: str = "Query must be a non-empty string.") -> None:
        super().__init__(detail=detail, status_code=status.HTTP_400_BAD_REQUEST)


class DuplicateDocumentError(AppError):
    """Returned when the same document already exists and re-upload is idempotent."""
    error_code = "DOCUMENT_EXISTS"

    def __init__(self, document_id: str) -> None:
        super().__init__(
            detail=f"Document '{document_id}' already exists. Use the existing document_id.",
            status_code=status.HTTP_409_CONFLICT,
        )


# ── 401/403 Auth ───────────────────────────────────────────────────────────────
class AuthenticationError(AppError):
    error_code = "AUTHENTICATION_FAILED"

    def __init__(self, detail: str = "Invalid or missing authentication credentials.") -> None:
        super().__init__(detail=detail, status_code=status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(AppError):
    error_code = "AUTHORIZATION_FAILED"

    def __init__(self, detail: str = "You do not have permission to access this resource.") -> None:
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN)


# ── 502/503 Provider Errors ────────────────────────────────────────────────────
class ProviderError(AppError):
    """Raised when an external provider (ADE, OpenRouter, Groq) fails."""
    error_code = "PROVIDER_ERROR"

    def __init__(self, provider: str, detail: str) -> None:
        super().__init__(
            detail=f"Provider '{provider}' error: {detail}",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class ProviderTimeoutError(ProviderError):
    error_code = "PROVIDER_TIMEOUT"

    def __init__(self, provider: str) -> None:
        super().__init__(provider=provider, detail="Request timed out.")


class AllProvidersFailedError(AppError):
    error_code = "ALL_PROVIDERS_FAILED"

    def __init__(self) -> None:
        super().__init__(
            detail="All LLM providers (Groq, OpenRouter) failed. Please try again later.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ── Ingestion Errors ───────────────────────────────────────────────────────────
class IngestionError(AppError):
    error_code = "INGESTION_FAILED"

    def __init__(self, document_id: str, detail: str) -> None:
        super().__init__(
            detail=f"Ingestion failed for document '{document_id}': {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
