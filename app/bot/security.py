import hashlib
import hmac

from app.core.config import settings


def make_join_payload(group_id: int) -> str:
    raw = str(group_id)
    signature = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"join_{raw}_{signature}"


def parse_join_payload(payload: str) -> int | None:
    parts = payload.split("_")
    if len(parts) != 3 or parts[0] != "join":
        return None
    raw_group_id, provided_signature = parts[1], parts[2]
    if not raw_group_id.isdigit():
        return None
    expected_signature = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        raw_group_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None
    return int(raw_group_id)
