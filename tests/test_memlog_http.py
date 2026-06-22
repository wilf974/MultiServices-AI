"""Regression : le client construit un corps signe verifiable, avec nonce unique et ts ISO."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from multiservice.memlog_http import build_request

KEY = "deadbeefcafe"
NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_build_request_signed_and_wellformed():
    body, sig = build_request("ma note", "note", "sujet", KEY, now=NOW)
    payload = json.loads(body)
    assert payload["text"] == "ma note" and payload["kind"] == "note" and payload["session"] == "sujet"
    assert payload["ts"] == NOW.isoformat() and payload["nonce"]
    assert hmac.new(KEY.encode(), body, hashlib.sha256).hexdigest() == sig


def test_build_request_nonce_unique():
    b1, _ = build_request("x", "note", "s", KEY)
    b2, _ = build_request("x", "note", "s", KEY)
    assert json.loads(b1)["nonce"] != json.loads(b2)["nonce"]
