from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(64 * 1024)))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "600"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "60"))
SLOW_REQUEST_MS = float(os.getenv("SLOW_REQUEST_MS", "500"))

EXEMPT_PATHS = ("/health", "/metrics")


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    entry = {
        "service": "backend",
        "event": event,
        "level": level,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        **fields,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(entry, ensure_ascii=False), file=stream, flush=True)


class Metrics:
    def __init__(self, window: int = 1000) -> None:
        self._lock = threading.Lock()
        self.requests_total = 0
        self.errors_total = 0
        self.rejected_rate_limit = 0
        self.rejected_too_large = 0
        self.by_path: dict[str, int] = defaultdict(int)
        self.by_status: dict[int, int] = defaultdict(int)
        self._latencies: deque[float] = deque(maxlen=window)
        self.started_at = time.time()

    def observe(self, path: str, status: int, ms: float) -> None:
        with self._lock:
            self.requests_total += 1
            self.by_path[path] += 1
            self.by_status[status] += 1
            self._latencies.append(ms)
            if status >= 500:
                self.errors_total += 1

    def note_rate_limited(self) -> None:
        with self._lock:
            self.rejected_rate_limit += 1

    def note_too_large(self) -> None:
        with self._lock:
            self.rejected_too_large += 1

    def _percentile(self, values: list[float], q: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, int(q * len(values)))
        return values[index]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = sorted(self._latencies)
            uptime = time.time() - self.started_at
            return {
                "uptime_seconds": round(uptime, 1),
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "requests_per_second": round(self.requests_total / uptime, 3)
                if uptime > 0
                else 0.0,
                "rejected_rate_limit": self.rejected_rate_limit,
                "rejected_too_large": self.rejected_too_large,
                "latency_ms": {
                    "count": len(latencies),
                    "p50": round(self._percentile(latencies, 0.50), 2),
                    "p90": round(self._percentile(latencies, 0.90), 2),
                    "p99": round(self._percentile(latencies, 0.99), 2),
                    "max": round(latencies[-1], 2) if latencies else 0.0,
                },
                "by_status": dict(sorted(self.by_status.items())),
                "top_paths": dict(
                    sorted(self.by_path.items(), key=lambda kv: -kv[1])[:10]
                ),
            }

    def reset(self) -> None:
        with self._lock:
            self.requests_total = 0
            self.errors_total = 0
            self.rejected_rate_limit = 0
            self.rejected_too_large = 0
            self.by_path.clear()
            self.by_status.clear()
            self._latencies.clear()
            self.started_at = time.time()


metrics = Metrics()


class TokenBucket:

    def __init__(self, rate_per_minute: int, burst: int) -> None:
        self.rate = rate_per_minute / 60.0
        self.burst = burst
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = TokenBucket(RATE_LIMIT_PER_MINUTE, RATE_LIMIT_BURST)


def _client_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key[:16]}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        path = request.url.path
        started = time.perf_counter()

        if path not in EXEMPT_PATHS:
            declared = request.headers.get("content-length")
            if declared and int(declared) > MAX_BODY_BYTES:
                metrics.note_too_large()
                log_event(
                    "request_rejected",
                    "warning",
                    request_id=request_id,
                    path=path,
                    reason="body_too_large",
                    bytes=int(declared),
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"request body exceeds {MAX_BODY_BYTES} bytes"
                    },
                    headers={"X-Request-ID": request_id},
                )

            if not limiter.allow(_client_key(request)):
                metrics.note_rate_limited()
                log_event(
                    "request_rejected",
                    "warning",
                    request_id=request_id,
                    path=path,
                    reason="rate_limited",
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "too many requests"},
                    headers={
                        "X-Request-ID": request_id,
                        "Retry-After": "1",
                    },
                )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000.0
            metrics.observe(path, 500, elapsed)
            log_event(
                "request_failed",
                "error",
                request_id=request_id,
                method=request.method,
                path=path,
                duration_ms=round(elapsed, 2),
                error=str(exc),
            )
            raise

        elapsed = (time.perf_counter() - started) * 1000.0
        metrics.observe(path, response.status_code, elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed:.1f}"

        if path not in EXEMPT_PATHS and (
            elapsed > SLOW_REQUEST_MS or response.status_code >= 400
        ):
            log_event(
                "request_slow" if elapsed > SLOW_REQUEST_MS else "request_error",
                "warning",
                request_id=request_id,
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=round(elapsed, 2),
            )
        return response
