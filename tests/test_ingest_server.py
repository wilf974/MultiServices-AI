"""Regression : la route POST /ingest mappe la logique d'ingest sur les bons codes HTTP."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient

from multiservice.ingest_server import build_app

KEY = "deadbeefcafe"


def _client(tmp_path):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"bureau": {"source": "project:bureau", "hmac_key": KEY}}), encoding="utf-8")
    app = build_app(registry_path=str(reg), journal_path=str(tmp_path / "j.jsonl"),
                    nonce_path=str(tmp_path / "n.jsonl"))
    return TestClient(app)


def _post(client, body: bytes, cn="bureau", key=KEY):
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/ingest", content=body,
                       headers={"X-Client-CN": cn, "X-Mem-Signature": sig,
                                "Content-Type": "application/json"})


def test_post_ingest_created(tmp_path):
    from datetime import datetime, timezone
    c = _client(tmp_path)
    body = json.dumps({"text": "ok", "kind": "note", "session": "s",
                       "ts": datetime.now(timezone.utc).isoformat(), "nonce": "z1"}).encode()
    r = _post(c, body)
    assert r.status_code == 201
    assert r.json()["source"] == "project:bureau"


def test_post_ingest_bad_json_422(tmp_path):
    c = _client(tmp_path)
    r = _post(c, b"{not json}")
    assert r.status_code == 422


def test_post_ingest_unknown_cn_401(tmp_path):
    from datetime import datetime, timezone
    c = _client(tmp_path)
    body = json.dumps({"text": "x", "kind": "note", "session": "s",
                       "ts": datetime.now(timezone.utc).isoformat(), "nonce": "z2"}).encode()
    r = _post(c, body, cn="inconnu")
    assert r.status_code == 401
