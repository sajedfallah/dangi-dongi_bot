from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.api_security import authenticate_request
from app.core.config import settings


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)

        try:
            auth = authenticate_request(request)
        except Exception as exc:
            status_code = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "authentication required")
            return JSONResponse(status_code=status_code, content={"detail": detail})

        request.state.auth = auth
        if auth.kind != "service":
            client_ip = request.client.host if request.client else "unknown"
            identity = str(auth.telegram_id) if auth.telegram_id is not None else client_ip
            key = f"{auth.kind}:{identity}"
            now = time.monotonic()
            cutoff = now - settings.rate_limit_window_seconds
            async with self._lock:
                bucket = self._hits[key]
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= settings.rate_limit_requests:
                    retry_after = max(1, int(settings.rate_limit_window_seconds - (now - bucket[0])))
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "rate limit exceeded"},
                        headers={"Retry-After": str(retry_after)},
                    )
                bucket.append(now)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response
