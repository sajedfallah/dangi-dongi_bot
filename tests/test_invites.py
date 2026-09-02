from app.bot.security import make_join_payload, parse_join_payload


def test_signed_join_payload_roundtrip():
    payload = make_join_payload(42)
    assert payload.startswith("join_42_")
    assert parse_join_payload(payload) == 42


def test_tampered_join_payload_is_rejected():
    payload = make_join_payload(42)
    tampered = payload.replace("join_42_", "join_43_", 1)
    assert parse_join_payload(tampered) is None


def test_invalid_join_payload_is_rejected():
    assert parse_join_payload("join_abc_bad") is None
    assert parse_join_payload("anything") is None
