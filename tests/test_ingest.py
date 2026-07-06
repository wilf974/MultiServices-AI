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


def test_secret_rejete_422(tmp_path):
    """Garde anti-secret (kit LLM universel) : une VALEUR de cle/jeton est refusee AVANT append.
    Un secret dans un journal append-only est ineffacable -> on ne l'ecrit jamais."""
    jp = tmp_path / "j.jsonl"
    p = _payload(text="ma cle est sk-ABCDEF0123456789")
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 422 and "secret" in r["error"]
    assert not jp.exists() or read_events(str(jp)) == []


def test_secret_force_true_passe(tmp_path):
    """Contournement VOLONTAIRE (C1) : force=true dans le corps signe -> 201 (l'humain assume)."""
    jp = tmp_path / "j.jsonl"
    p = _payload(text="rotation effectuee de sk-ABCDEF0123456789", force=True)
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 201


def test_mention_et_ip_ne_bloquent_pas(tmp_path):
    """Conservateur : une mention ('anti-secret', 'token JWT') ou une IP legitime passe (201)."""
    jp = tmp_path / "j.jsonl"
    p = _payload(text="garde anti-secret livree ; deploiement VPS <VPS_LAN>")
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 201


def test_closes_valide_passe_et_atterrit_dans_l_event(tmp_path):
    """Curation Phase 2 : une cloture ciblee signee (kind=correction) -> 201, data.closes pose."""
    jp = tmp_path / "j.jsonl"
    p = _payload(kind="correction", text="curation approuvee : cloture de doublons",
                 data={"closes": ["id-a", "id-b"]})
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 201
    evs = read_events(str(jp))
    assert evs[0].data.get("closes") == ["id-a", "id-b"]


def test_closes_invalide_ou_mauvais_kind_422(tmp_path):
    ns = ing.NonceStore(tmp_path / "n")
    # pas une liste d'ids -> 422
    p1 = _payload(kind="correction", text="cloture cassee",
                  data={"closes": "id-a"}, nonce="nA")
    b1 = json.dumps(p1).encode()
    r1 = ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(tmp_path / "j"), ns, now=NOW)
    assert r1["status"] == 422 and "closes" in r1["error"]
    # closes sur un kind non-correction -> 422 (sinon cloture inerte cote lecture)
    p2 = _payload(kind="note", text="cloture via note interdite",
                  data={"closes": ["id-a"]}, nonce="nB")
    b2 = json.dumps(p2).encode()
    r2 = ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(tmp_path / "j"), ns, now=NOW)
    assert r2["status"] == 422 and "correction" in r2["error"]


def test_dedup_meme_texte_source_kind_skip_200(tmp_path):
    """Cause racine des doublons (agent re-journalisant) : un fait VIVANT au meme
    texte/source/kind n'est PAS re-appende -> 200 duplicate, id existant, journal inchange."""
    jp = tmp_path / "j.jsonl"; ns = ing.NonceStore(tmp_path / "n.jsonl")
    p1 = _payload(text="[FABLE5] invariant a re-logger", nonce="n1")
    b1 = json.dumps(p1).encode()
    r1 = ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(jp), ns, now=NOW)
    assert r1["status"] == 201
    p2 = _payload(text="[FABLE5] invariant a re-logger", nonce="n2")
    b2 = json.dumps(p2).encode()
    r2 = ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(jp), ns, now=NOW)
    assert r2["status"] == 200 and r2.get("duplicate") is True
    assert r2["id"] == r1["id"]                       # pointe l'original
    assert len(read_events(str(jp))) == 1            # rien de re-appende


def test_dedup_force_true_reappend_201(tmp_path):
    """Contournement VOLONTAIRE (C1) : force=true re-appende malgre le doublon."""
    jp = tmp_path / "j.jsonl"; ns = ing.NonceStore(tmp_path / "n.jsonl")
    p1 = _payload(text="fait duplicable", nonce="n1"); b1 = json.dumps(p1).encode()
    assert ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(jp), ns, now=NOW)["status"] == 201
    p2 = _payload(text="fait duplicable", force=True, nonce="n2"); b2 = json.dumps(p2).encode()
    assert ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(jp), ns, now=NOW)["status"] == 201
    assert len(read_events(str(jp))) == 2


def test_dedup_texte_different_passe(tmp_path):
    jp = tmp_path / "j.jsonl"; ns = ing.NonceStore(tmp_path / "n.jsonl")
    p1 = _payload(text="fait A", nonce="n1"); b1 = json.dumps(p1).encode()
    assert ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(jp), ns, now=NOW)["status"] == 201
    p2 = _payload(text="fait B", nonce="n2"); b2 = json.dumps(p2).encode()
    assert ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(jp), ns, now=NOW)["status"] == 201
    assert len(read_events(str(jp))) == 2


def test_dedup_ne_matche_pas_autre_kind(tmp_path):
    """Meme texte mais kind different = pas un doublon (une decision != une note)."""
    jp = tmp_path / "j.jsonl"; ns = ing.NonceStore(tmp_path / "n.jsonl")
    p1 = _payload(text="meme phrase", kind="decision", nonce="n1"); b1 = json.dumps(p1).encode()
    assert ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(jp), ns, now=NOW)["status"] == 201
    p2 = _payload(text="meme phrase", kind="note", nonce="n2"); b2 = json.dumps(p2).encode()
    assert ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(jp), ns, now=NOW)["status"] == 201
    assert len(read_events(str(jp))) == 2


def test_dedup_seulement_contre_les_vivants(tmp_path):
    """Un original CLOS (C3) ne bloque pas une re-affirmation : dedup vs faits vivants seulement."""
    jp = tmp_path / "j.jsonl"; ns = ing.NonceStore(tmp_path / "n.jsonl")
    p1 = _payload(text="fait revocable", nonce="n1"); b1 = json.dumps(p1).encode()
    id1 = ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(jp), ns, now=NOW)["id"]
    # cloture ciblee de l'original (curation Phase 2)
    pc = _payload(kind="correction", text="cloture de fait revocable",
                  data={"closes": [id1]}, nonce="n2")
    bc = json.dumps(pc).encode()
    assert ing.ingest(pc, "bureau", _sign(bc), bc, REG, str(jp), ns, now=NOW)["status"] == 201
    # re-affirmer le meme texte : l'original est clos -> ce n'est plus un doublon vivant -> 201
    p3 = _payload(text="fait revocable", nonce="n3"); b3 = json.dumps(p3).encode()
    assert ing.ingest(p3, "bureau", _sign(b3), b3, REG, str(jp), ns, now=NOW)["status"] == 201


def test_find_live_duplicate_texte_vide_renvoie_none(tmp_path):
    assert ing.find_live_duplicate([], "project:bureau", "note", "   ", NOW) is None


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
