"""Lightweight in-process metrics: per-request TTFA/total timing + active connection tracking.

We deliberately avoid a full Prometheus exporter in v1 — the plan calls for
TTFA logging and a `/health` snapshot. If we grow to multi-instance later,
swap this for prometheus_client.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional

logger = logging.getLogger("tts_api.metrics")


@dataclass
class RequestTimings:
    request_id: str
    model: str
    started_at: float
    first_chunk_at: Optional[float] = None
    finished_at: Optional[float] = None
    bytes_out: int = 0
    error: Optional[str] = None

    @property
    def ttfa_ms(self) -> Optional[int]:
        if self.first_chunk_at is None:
            return None
        return int((self.first_chunk_at - self.started_at) * 1000)

    @property
    def total_ms(self) -> Optional[int]:
        if self.finished_at is None:
            return None
        return int((self.finished_at - self.started_at) * 1000)

    def mark_first_chunk(self) -> None:
        if self.first_chunk_at is None:
            self.first_chunk_at = time.perf_counter()

    def mark_finished(self, error: Optional[str] = None) -> None:
        self.finished_at = time.perf_counter()
        if error:
            self.error = error


@dataclass
class MetricsRegistry:
    """Process-wide counter of active connections and last-N request log."""
    _active: int = 0
    _lock: Lock = field(default_factory=Lock)
    _recent: Dict[str, RequestTimings] = field(default_factory=dict)
    _max_recent: int = 200

    @property
    def active_connections(self) -> int:
        with self._lock:
            return self._active

    def new_request(self, model: str) -> RequestTimings:
        req = RequestTimings(
            request_id=str(uuid.uuid4()),
            model=model,
            started_at=time.perf_counter(),
        )
        with self._lock:
            self._recent[req.request_id] = req
            # Trim oldest if we exceed cap.
            if len(self._recent) > self._max_recent:
                oldest = next(iter(self._recent))
                self._recent.pop(oldest, None)
        return req

    @contextmanager
    def track_connection(self):
        with self._lock:
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1

    def log_completion(self, req: RequestTimings) -> None:
        logger.info(
            "tts_request_complete",
            extra={
                "request_id": req.request_id,
                "model": req.model,
                "ttfa_ms": req.ttfa_ms,
                "total_ms": req.total_ms,
                "bytes_out": req.bytes_out,
                "error": req.error,
            },
        )


# Module-level singleton. Import this everywhere.
registry = MetricsRegistry()
