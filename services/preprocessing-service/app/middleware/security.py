from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security_events import emit_security_event


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= now - window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limit: int,
        window_seconds: int,
        path_prefix: str = "/preprocessing",
    ) -> None:
        super().__init__(app)
        self._limit = limit
        self._window_seconds = window_seconds
        self._path_prefix = path_prefix
        self._limiter = InMemoryRateLimiter()

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self._path_prefix):
            client_host = request.client.host if request.client else "unknown"
            allowed, retry_after = self._limiter.allow(
                key=client_host,
                limit=self._limit,
                window_seconds=self._window_seconds,
            )
            if not allowed:
                settings = getattr(request.app.state, "settings", None)
                emit_security_event(
                    getattr(settings, "security_base_url", ""),
                    source_service=getattr(settings, "app_name", "preprocessing-service"),
                    event_type="RATE_LIMIT_EXCEEDED",
                    severity="warning",
                    title="Rate limit exceeded",
                    message="A client exceeded the preprocessing request threshold.",
                    metadata={
                        "client_ip": client_host,
                        "path": request.url.path,
                        "retry_after": retry_after,
                    },
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_request_size_bytes: int) -> None:
        super().__init__(app)
        self._max_request_size_bytes = max_request_size_bytes

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            raw_content_length = request.headers.get("content-length")
            if raw_content_length:
                try:
                    content_length = int(raw_content_length)
                except ValueError:
                    return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
                if content_length > self._max_request_size_bytes:
                    settings = getattr(request.app.state, "settings", None)
                    emit_security_event(
                        getattr(settings, "security_base_url", ""),
                        source_service=getattr(settings, "app_name", "preprocessing-service"),
                        event_type="REQUEST_SIZE_LIMIT_EXCEEDED",
                        severity="warning",
                        title="Request body too large",
                        message="A client sent a request larger than the configured preprocessing limit.",
                        metadata={
                            "path": request.url.path,
                            "content_length": content_length,
                            "max_request_size_bytes": self._max_request_size_bytes,
                        },
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
        return await call_next(request)
