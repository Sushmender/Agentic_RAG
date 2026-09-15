"""
backend/app/core/retries.py
Tenacity-based retry and timeout decorators for provider calls.
All retry parameters come from Settings to keep configuration centralized.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, Type, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    retry_on: tuple[Type[Exception], ...] = (Exception,),
    provider_name: str = "unknown",
) -> Callable[[F], F]:
    """
    Decorator: retry async function on specified exceptions with exponential backoff.

    Usage:
        @with_retry(max_attempts=3, provider_name="OpenRouter")
        async def call_openrouter(...): ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            try:
                async for attempt_obj in AsyncRetrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential(multiplier=wait_min, max=wait_max),
                    retry=retry_if_exception_type(retry_on),
                    reraise=True,
                ):
                    with attempt_obj:
                        attempt += 1
                        if attempt > 1:
                            logger.warning(
                                "Retrying provider call",
                                provider=provider_name,
                                function=func.__name__,
                                attempt=attempt,
                            )
                        return await func(*args, **kwargs)
            except RetryError as exc:
                logger.error(
                    "All retry attempts exhausted",
                    provider=provider_name,
                    function=func.__name__,
                    max_attempts=max_attempts,
                )
                raise exc.last_attempt.result() from exc  # type: ignore[union-attr]
        return wrapper  # type: ignore[return-value]
    return decorator  # type: ignore[return-value]


async def with_timeout(
    coro: Any,
    timeout_seconds: float,
    provider_name: str = "unknown",
) -> Any:
    """Run a coroutine with a timeout, logging on failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(
            "Provider call timed out",
            provider=provider_name,
            timeout_seconds=timeout_seconds,
        )
        raise
