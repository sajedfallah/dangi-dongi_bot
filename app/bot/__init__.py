import httpx

from app.core.config import settings


_OriginalAsyncClient = httpx.AsyncClient


class _ServiceAsyncClient(_OriginalAsyncClient):
    def __init__(self, *args, headers=None, **kwargs):
        merged_headers = {"X-Service-Token": settings.service_api_token}
        if headers:
            merged_headers.update(dict(headers))
        super().__init__(*args, headers=merged_headers, **kwargs)


# Importing app.bot happens only inside the Telegram bot process. Keeping the
# internal service credential here avoids exposing it to Telegram clients or
# requiring every handler to remember the authentication header.
httpx.AsyncClient = _ServiceAsyncClient
