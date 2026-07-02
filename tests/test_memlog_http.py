"""Regression : le client construit un corps signe verifiable, avec nonce unique et ts ISO."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import ssl

import httpx
import pytest

import multiservice.memlog_http as memlog_http
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


def test_main_porte_le_cert_via_sslcontext(monkeypatch):
    """Regression httpx>=0.28 : le cert client passe par un SSLContext (load_cert_chain),
    JAMAIS via un argument cert= sur post() (supprime en 0.28 -> TypeError en prod)."""
    rec = {}

    class FakeCtx:
        def load_cert_chain(self, certfile, keyfile):
            rec["cert"] = (certfile, keyfile)

    class FakeResp:
        status_code = 201
        text = "ok"

    class FakeClient:
        def __init__(self, **kw):
            rec["client_kw"] = kw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kw):
            rec["url"] = url
            rec["post_kw"] = kw
            return FakeResp()

    monkeypatch.setattr(ssl, "create_default_context", lambda: FakeCtx())
    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setenv("MEM_INGEST_URL", "https://mem.example/ingest")
    monkeypatch.setenv("MEM_HMAC_KEY", KEY)
    monkeypatch.setenv("MEM_CLIENT_CERT", "c.pem")
    monkeypatch.setenv("MEM_CLIENT_KEY", "k.pem")
    monkeypatch.setattr("sys.argv", ["memlog-http", "hello", "--kind", "note", "--session", "s"])

    memlog_http.main()

    assert "cert" not in rec["post_kw"], "post() ne doit PAS recevoir cert= (httpx>=0.28)"
    assert rec["client_kw"].get("verify") is not None, "le cert doit etre porte par verify=SSLContext"
    assert rec["cert"] == ("c.pem", "k.pem"), "load_cert_chain doit charger le cert client"
    assert rec["url"] == "https://mem.example/ingest"
    assert rec["post_kw"]["headers"]["X-Mem-Signature"]


def test_main_refuse_le_gabarit_non_rempli(monkeypatch, capsys):
    """Garde anti-placeholder : refus AVANT le reseau (exit 2), message explicite."""
    monkeypatch.setenv("MEM_INGEST_URL", "https://mem.example/ingest")
    monkeypatch.setenv("MEM_HMAC_KEY", KEY)
    monkeypatch.setenv("MEM_CLIENT_CERT", "c.pem")
    monkeypatch.setenv("MEM_CLIENT_KEY", "k.pem")
    monkeypatch.setattr("sys.argv", ["memlog-http", "<le fait, texte reel>", "--kind", "note"])
    with pytest.raises(SystemExit) as ei:
        memlog_http.main()
    assert ei.value.code == 2
    assert "gabarit" in capsys.readouterr().out


def test_build_request_porte_force_seulement_si_demande():
    """--force voyage DANS le corps signe (le serveur le lit) ; absent par defaut (compat)."""
    body, _ = build_request("<FAIT>", "note", "s", KEY, force=True)
    assert json.loads(body)["force"] is True
    body2, _ = build_request("vrai texte", "note", "s", KEY)
    assert "force" not in json.loads(body2)
