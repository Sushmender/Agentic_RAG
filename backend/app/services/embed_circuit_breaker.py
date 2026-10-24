"""
backend/app/services/embed_circuit_breaker.py
In-process circuit breaker for the embedding provider.

State machine (per-process singleton):
  CLOSED  ->  after 2 consecutive failures within 60 s  ->  OPEN
  OPEN    ->  after 60 s                                ->  HALF_OPEN
  HALF_OPEN ->  probe succeeds                          ->  CLOSED
  HALF_OPEN ->  probe fails                             ->  OPEN (reset timer)

Rules:
  - While OPEN, no provider calls are made; callers get EmbedCircuitOpenError.
  - While HALF_OPEN, exactly one probe is allowed; subsequent callers get EmbedCircuitOpenError.
  - While OPEN/HALF_OPEN, hedging is disabled by the caller checking is_open().
  - State changes are logged with structlog.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Configuration constants
_FAILURE_THRESHOLD    = 2     # consecutive failures to open
_FAILURE_WINDOW_S     = 60    # failures must occur within this window
_OPEN_DURATION_S      = 60    # how long breaker stays open before probe
_HALF_OPEN_PROBE_LOCK = True  # only one probe at a time


class BreakerState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class EmbedCircuitOpenError(RuntimeError):
    """Raised when the embed circuit breaker is open and no call should be made."""
    pass


class EmbeddingCircuitBreaker:
    """
    Thread/async-safe (single-process) circuit breaker for the embedding provider.
    Not asyncio-lock-protected — state transitions are fast Python operations which
    are atomic in CPython's GIL, sufficient for this in-process use.
    """

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        failure_window_s: float = _FAILURE_WINDOW_S,
        open_duration_s: float = _OPEN_DURATION_S,
    ) -> None:
        self._state: BreakerState = BreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_ts: float = 0.0
        self._opened_at: float = 0.0
        self._probe_in_flight: bool = False

        self.failure_threshold = failure_threshold
        self.failure_window_s  = failure_window_s
        self.open_duration_s   = open_duration_s

    # ── Public state checks ───────────────────────────────────────────────────

    @property
    def state(self) -> BreakerState:
        self._maybe_transition_to_half_open()
        return self._state

    def is_open(self) -> bool:
        """True if no provider call should be made (OPEN or HALF_OPEN with probe in flight)."""
        s = self.state  # may trigger HALF_OPEN transition
        if s == BreakerState.CLOSED:
            return False
        if s == BreakerState.OPEN:
            return True
        # HALF_OPEN: allow exactly one probe
        if self._probe_in_flight:
            return True
        return False

    def try_acquire_probe(self) -> bool:
        """
        Called before attempting a probe request while HALF_OPEN.
        Returns True if this caller should make the probe, False otherwise.
        """
        s = self.state
        if s != BreakerState.HALF_OPEN:
            return False
        if self._probe_in_flight:
            return False
        self._probe_in_flight = True
        logger.info("EmbedCircuitBreaker: probe request started", state=self._state)
        return True

    # ── Outcome recording ─────────────────────────────────────────────────────

    def record_success(self) -> None:
        """Call after a successful embedding provider response."""
        if self._state in (BreakerState.HALF_OPEN, BreakerState.OPEN):
            logger.info(
                "EmbedCircuitBreaker: probe succeeded -> CLOSED",
                prev_state=self._state,
            )
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._probe_in_flight = False

    def record_failure(self) -> None:
        """Call after a failed embedding provider call."""
        now = time.monotonic()

        # Reset consecutive counter if the previous failure was too long ago
        if now - self._last_failure_ts > self.failure_window_s:
            self._consecutive_failures = 0

        self._consecutive_failures += 1
        self._last_failure_ts = now

        if self._state == BreakerState.HALF_OPEN:
            # Probe failed -> re-open
            self._state = BreakerState.OPEN
            self._opened_at = now
            self._probe_in_flight = False
            logger.warning(
                "EmbedCircuitBreaker: probe FAILED -> OPEN again",
                consecutive_failures=self._consecutive_failures,
            )
        elif self._consecutive_failures >= self.failure_threshold:
            if self._state != BreakerState.OPEN:
                self._state = BreakerState.OPEN
                self._opened_at = now
                logger.warning(
                    "EmbedCircuitBreaker: threshold reached -> OPEN",
                    consecutive_failures=self._consecutive_failures,
                    threshold=self.failure_threshold,
                    window_s=self.failure_window_s,
                )
        else:
            logger.info(
                "EmbedCircuitBreaker: failure recorded (not yet open)",
                consecutive_failures=self._consecutive_failures,
                threshold=self.failure_threshold,
            )

    # ── Internal transition ───────────────────────────────────────────────────

    def _maybe_transition_to_half_open(self) -> None:
        if self._state == BreakerState.OPEN:
            if time.monotonic() - self._opened_at >= self.open_duration_s:
                self._state = BreakerState.HALF_OPEN
                self._probe_in_flight = False
                logger.info(
                    "EmbedCircuitBreaker: open duration elapsed -> HALF_OPEN",
                    open_duration_s=self.open_duration_s,
                )


# Module-level singleton
embed_circuit_breaker = EmbeddingCircuitBreaker()
