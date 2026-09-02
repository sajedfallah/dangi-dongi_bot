from __future__ import annotations

import os
import sys

import httpx


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    service_token = os.getenv("SERVICE_API_TOKEN", "")
    if not service_token:
        fail("SERVICE_API_TOKEN is required")

    with httpx.Client(base_url=base_url, timeout=10) as client:
        health = client.get("/health")
        if health.status_code != 200:
            fail(f"/health returned {health.status_code}: {health.text}")
        print("OK: health")

        unauth = client.get("/api/v1/users/1/groups")
        if unauth.status_code != 401:
            fail(f"unauthenticated API should return 401, got {unauth.status_code}")
        print("OK: unauthenticated API blocked")

        headers = {"X-Service-Token": service_token}
        user = client.post(
            "/api/v1/users",
            headers=headers,
            json={"telegram_id": 990000001, "display_name": "Staging Smoke User"},
        )
        if user.status_code != 200:
            fail(f"service-auth user endpoint failed: {user.status_code}: {user.text}")
        print("OK: service token accepted")

    print("STAGING_SMOKE_OK")


if __name__ == "__main__":
    main()
