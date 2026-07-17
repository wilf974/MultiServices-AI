"""Opt-in chiffrement au repos au CHOKE POINT journal.py (Brief 1, branchement de bout en bout).

`MULTISERVICE_ENCRYPT=1` (config.ENCRYPT_AT_REST) -> `append_events` chiffre a l'ecriture
(slot-par-source) et `read_events` dechiffre par defaut. Un seul point de branchement : les
appelants (capture, ingest, mcp_server, projection...) ne changent pas. Les intents d'audit
(erasure/migration) restent EN CLAIR sur le disque (les chiffrer sous le slot qu'ils effacent
detruirait la trace avec la cle)."""
from multiservice import config, envelope, keyring
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(**kw):
    d = dict(type=EventType.NOTE, title="titre secret", description="desc secrete",
             source="human:local", data={"x": 1})
    d.update(kw)
    return AetherEvent(**d)


def _opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENCRYPT_AT_REST", True)
    monkeypatch.setattr(config, "KEYRING_DIR", str(tmp_path / "keyring"))


# ---- retro-compat : sans opt-in, RIEN ne change ----
def test_off_par_defaut_ecrit_en_clair(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev()])
    assert "titre secret" in journal.read_text(encoding="utf-8")
    assert read_events(journal)[0].title == "titre secret"


# ---- opt-in : chiffre a l'ecriture, dechiffre a la lecture, sans toucher les appelants ----
def test_optin_chiffre_a_l_ecriture_et_dechiffre_a_la_lecture(tmp_path, monkeypatch):
    _opt_in(monkeypatch, tmp_path)
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev()])
    raw = journal.read_text(encoding="utf-8")
    assert "titre secret" not in raw and "desc secrete" not in raw   # le disque ne voit pas le clair
    e = read_events(journal)[0]                                      # lecture par defaut = clair
    assert (e.title, e.description, e.data) == ("titre secret", "desc secrete", {"x": 1})


def test_optin_slot_par_source(tmp_path, monkeypatch):
    _opt_in(monkeypatch, tmp_path)
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev(source="human:a", title="secret a"),
                            _ev(source="human:b", title="secret b")])
    km = keyring.KeyManager(base=tmp_path / "keyring")
    km.destroy("slot:human:a")                                       # shred du slot d'UNE source
    evs = read_events(journal)
    by_source = {e.source: e for e in evs}
    assert by_source["human:a"].title == "[efface]"                  # tombstone
    assert by_source["human:b"].title == "secret b"                  # l'autre source intacte


def test_optin_erasure_reste_en_clair(tmp_path, monkeypatch):
    _opt_in(monkeypatch, tmp_path)
    journal = tmp_path / "j.jsonl"
    append_events(journal, [AetherEvent(type=EventType.ERASURE, title="erasure",
                                        source="human:operator", data={"targets": ["slot:x"]})])
    raw_ev = read_events(journal, keyring=None)[0]                   # lecture BRUTE explicite
    assert not envelope.is_encrypted(raw_ev)
    assert raw_ev.data["targets"] == ["slot:x"]                      # l'intent d'audit survit a tout shred


def test_optin_lecture_brute_explicite_reste_chiffree(tmp_path, monkeypatch):
    _opt_in(monkeypatch, tmp_path)
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev()])
    raw_ev = read_events(journal, keyring=None)[0]                   # keyring=None = brut, meme en opt-in
    assert envelope.is_encrypted(raw_ev) and raw_ev.title == ""


def test_optin_deja_chiffre_pas_de_double_enveloppe(tmp_path, monkeypatch):
    _opt_in(monkeypatch, tmp_path)
    from multiservice import encrypt
    journal = tmp_path / "j.jsonl"
    km = keyring.KeyManager(base=tmp_path / "keyring")
    enc = encrypt.encrypt_event(_ev(), "slot:custom", km)
    append_events(journal, [enc])                                    # deja chiffre par l'appelant
    raw_ev = read_events(journal, keyring=None)[0]
    assert raw_ev.data["enc"]["slot"] == "slot:custom"               # enveloppe d'origine, pas re-enveloppe
    assert read_events(journal)[0].title == "titre secret"
