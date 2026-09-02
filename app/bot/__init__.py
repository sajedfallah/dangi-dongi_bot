import os
import re


# Keep package imports side-effect free during API startup and tests. The
# dedicated run_bot.py launcher sets this flag before importing app.bot.main.
if os.getenv("DANGI_BOT_PROCESS") == "1":
    import httpx

    from app.core.config import settings

    _OriginalAsyncClient = httpx.AsyncClient
    _USER_GROUPS = re.compile(r"^/api/v1/users/(\d+)/groups$")

    class _ServiceAsyncClient(_OriginalAsyncClient):
        def __init__(self, *args, headers=None, **kwargs):
            merged_headers = {"X-Service-Token": settings.service_api_token}
            if headers:
                merged_headers.update(dict(headers))
            # Internal Bot -> API requests must never inherit OS HTTP(S) proxies.
            kwargs.setdefault("trust_env", False)
            super().__init__(*args, headers=merged_headers, **kwargs)

        async def get(self, url, *args, **kwargs):
            if isinstance(url, str):
                match = _USER_GROUPS.match(url)
                if match:
                    url = f"/api/v1/dashboard/users/{match.group(1)}/groups"
            return await super().get(url, *args, **kwargs)

        async def post(self, url, *args, **kwargs):
            if url == "/api/v1/groups":
                url = "/api/v1/dashboard/groups"
            return await super().post(url, *args, **kwargs)

    httpx.AsyncClient = _ServiceAsyncClient
