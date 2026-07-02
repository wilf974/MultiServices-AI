"""Regression ingest distant : auth (HMAC/CN), anti-rejeu (ts/nonce), provenance forcee, validation."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta

from multiservice import ingest as ing
from multiservice.journal import read_events

KEY = "deadbeefcafe"
REG = {"bureau": {"source": "project:bureau", "hmac_key": KEY}}
NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def _sign(body: bytes, key: str = KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _payload(**kw):
    p = {"text": "une decision", "kind": "decision", "session": "s",
         "ts": NOW.isoformat(), "nonce": "n1"}
    p.update(kw)
    return p


def test_verify_hmac_ok_and_ko():
    b = b'{"x":1}'
    assert ing.verify_hmac(b, _sign(b), KEY) is True
    assert ing.verify_hmac(b, "bad", KEY) is False
    assert ing.verify_hmac(b, _sign(b), "wrongkey") is False


def test_check_freshness_window():
    assert ing.check_freshness(NOW.isoformat(), NOW) is True
    assert ing.check_freshness((NOW - timedelta(seconds=600)).isoformat(), NOW) is False
    assert ing.check_freshness("pas une date", NOW) is False


def test_happy_path_appends_and_forces_source(tmp_path):
    jp = tmp_path / "j.jsonl"
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    p = _payload(source="project:HACKER")          # tentative d'usurpation
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)
    assert r["status"] == 201
    assert r["source"] == "project:bureau"          # source IMPOSEE par le CN, pas project:HACKER
    evs = read_events(str(jp))
    assert len(evs) == 1 and evs[0].source == "project:bureau"


def test_unknown_cn_rejected(tmp_path):
    p = _payload(); body = json.dumps(p).encode()
    r = ing.ingest(p, "inconnu", _sign(body), body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_bad_signature_rejected(tmp_path):
    p = _payload(); body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", "00" * 32, body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_stale_timestamp_rejected(tmp_path):
    p = _payload(ts=(NOW - timedelta(hours=1)).isoformat()); body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_replayed_nonce_rejected(tmp_path):
    jp = tmp_path / "j"; ns = ing.NonceStore(tmp_path / "n")
    p = _payload(); body = json.dumps(p).encode()
    assert ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)["status"] == 201
    assert ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)["status"] == 409


def test_invalid_kind_and_empty_text(tmp_path):
    ns = ing.NonceStore(tmp_path / "n")
    p1 = _payload(kind="evil"); b1 = json.dumps(p1).encode()
    assert ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(tmp_path / "j"), ns, now=NOW)["status"] == 422
    p2 = _payload(text="   ", nonce="n2"); b2 = json.dumps(p2).encode()
    assert ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(tmp_path / "j"), ns, now=NOW)["status"] == 422


def test_placeholder_rejete_422(tmp_path):
    """Gabarit non rempli (pollution observee au journal) -> 422, rien n'est appende."""
    jp = tmp_path / "j.jsonl"
    p = _payload(text="<le fait, texte reel>")
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 422 and "placeholder" in r["error"]
    assert not jp.exists() or read_events(str(jp)) == []


def test_placeholder_force_true_passe(tmp_path):
    """Contournement VOLONTAIRE (C1) : force=true dans le corps signe -> 201."""
    jp = tmp_path / "j.jsonl"
    p = _payload(text="<le fait, texte reel>", force=True)
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 201
    assert len(read_events(str(jp))) == 1


def test_nonce_store_prune(tmp_path):
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    ns.add("old", (NOW - timedelta(hours=1)).isoformat())
    ns.add("fresh", NOW.isoformat())
    ns.prune(NOW, window_s=300)
    assert ns.seen("old") is False and ns.seen("fresh") is True


def test_missing_nonce_is_422(tmp_path):
    """Nonce absent -> 422 (pas 409 qui est reserve au rejeu)."""
    jp = tmp_path / "j.jsonl"
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    p = _payload()
    del p["nonce"]
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)
    assert r["status"] == 422
    assert r["error"] == "missing nonce"


def test_ingest_prunes_old_nonces(tmp_path):
    """Apres un ingest valide, les anciens nonces hors-fenetre sont purges."""
    jp = tmp_path / "j.jsonl"
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    old_ts = (NOW - timedelta(hours=1)).isoformat()
    ns.add("vieux", old_ts)
    p = _payload(nonce="frais")
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)
    assert r["status"] == 201
    assert ns.seen("vieux") is False
    assert ns.seen("frais") is True
