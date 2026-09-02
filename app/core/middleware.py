from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.api_security import authenticate_request
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import GroupMember, User

_GROUP_RE = re.compile(r"^/api/v1/groups/(\d+)(?:/|$)")
_USER_GROUPS_RE = re.compile(r"^/api/v1/users/(\d+)/groups$")


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def _telegram_identity_guard(self, request: Request, telegram_id: int):
        body = {}
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                raw = await request.body()
                if raw:
                    body = json.loads(raw)
            except Exception:
                body = {}

        async with SessionLocal() as session:
            internal_user_id = (await session.execute(
                select(User.id).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()

            if request.url.path == "/api/v1/users" and request.method == "POST":
                claimed_telegram_id = body.get("telegram_id")
                if claimed_telegram_id is not None and int(claimed_telegram_id) != telegram_id:
                    return JSONResponse(status_code=403, content={"detail": "Telegram identity mismatch"})
                return None

            if internal_user_id is None:
                return JSONResponse(status_code=403, content={"detail": "Telegram user is not registered"})

            actor = body.get("actor_user_id")
            if actor is not None and int(actor) != internal_user_id:
                return JSONResponse(status_code=403, content={"detail": "actor identity mismatch"})

            query_actor = request.query_params.get("actor_user_id")
            if query_actor is not None and int(query_actor) != internal_user_id:
                return JSONResponse(status_code=403, content={"detail": "actor identity mismatch"})

            user_groups_match = _USER_GROUPS_RE.match(request.url.path)
            if user_groups_match and int(user_groups_match.group(1)) != internal_user_id:
                return JSONResponse(status_code=403, content={"detail": "user identity mismatch"})

            if request.url.path == "/api/v1/groups" and request.method == "POST":
                if int(body.get("owner_user_id", -1)) != internal_user_id:
                    return JSONResponse(status_code=403, content={"detail": "owner identity mismatch"})

            group_match = _GROUP_RE.match(request.url.path)
            if group_match:
                group_id = int(group_match.group(1))
                is_member = (await session.execute(select(GroupMember.id).where(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == internal_user_id,
                ))).scalar_one_or_none()

                is_join = request.method == "POST" and request.url.path == f"/api/v1/groups/{group_id}/members"
                if is_join:
                    if int(body.get("user_id", -1)) != internal_user_id:
                        return JSONResponse(status_code=403, content={"detail": "member identity mismatch"})
                elif is_member is None:
                    return JSONResponse(status_code=403, content={"detail": "group membership required"})

        request.state.internal_user_id = internal_user_id
        return None

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

        if auth.kind == "telegram" and auth.telegram_id is not None:
            denied = await self._telegram_identity_guard(request, auth.telegram_id)
            if denied is not None:
                return denied

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
