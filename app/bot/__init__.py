import os


# Keep package imports side-effect free during API startup and tests. The
# dedicated run_bot.py launcher sets this flag before importing app.bot.main.
if os.getenv("DANGI_BOT_PROCESS") == "1":
    import httpx

    from app.core.config import settings

    _OriginalAsyncClient = httpx.AsyncClient

    class _ServiceAsyncClient(_OriginalAsyncClient):
        def __init__(self, *args, headers=None, **kwargs):
            merged_headers = {"X-Service-Token": settings.service_api_token}
            if headers:
                merged_headers.update(dict(headers))
            # Internal Bot -> API traffic must never inherit system HTTP(S)
            # proxy settings. On some Windows environments, 127.0.0.1 is sent
            # through a configured proxy and returns 503 instead of reaching
            # the local FastAPI service.
            kwargs.setdefault("trust_env", False)
            super().__init__(*args, headers=merged_headers, **kwargs)

    httpx.AsyncClient = _ServiceAsyncClient
