"""P0 chiffrement au repos + crypto-shredding — tests d'integration (les 8 de docs/ENCRYPTION-AT-REST.md).

Ce fichier couvre le cycle complet : chiffrer -> journal -> dechiffrer, effacement crash-safe, censure,
purge d'index, rotation = re-wrap. Chaque test ecrit dans un journal jetable (tmp_path)."""
from datetime import datetime, timezone

import pytest

from multiservice import crypto, encrypt, erase, integrity, keyring
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events
from multiservice.semantic import EmbeddingStore


def _ev(**kw):
    d = dict(type=EventType.NOTE, title="titre secret", description="desc secrete",
             source="human:local", data={"x": 1})
    d.update(kw)
    return AetherEvent(**d)


def _km(tmp):
    return keyring.KeyManager(base=tmp / "keyring")


def _append_encrypted(journal, slot, km, **ev):
    """Chiffre + append. Retourne l'event ORIGINAL (clair) pour les assertions."""
    e = _ev(**ev)
    append_events(journal, [encrypt.encrypt_event(e, slot, km)])
    return e


def _raw_line(journal, eid):
    for ln in journal.read_text(encoding="utf-8").splitlines():
        if eid in ln:
            return ln
    return None


# ---- test 1 : roundtrip A TRAVERS LE DISQUE (mord la garde ⑥ si un datetime revient dans l'AAD) ----
def test_1_roundtrip(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    e = _ev(observed_at=datetime(2026, 7, 7, 12, 0, 0, 123456, tzinfo=timezone.utc))  # µs non-nulles
    append_events(journal, [encrypt.encrypt_event(e, "slot:a", km)])
    d = encrypt.decrypt_or_tombstone(read_events(journal)[0], km)
    assert (d.title, d.description, d.data) == ("titre secret", "desc secrete", {"x": 1})


# ---- test 2 : liaison AAD = ATTAQUE (IntegrityError), pas tombstone ----
def test_2_aad_binding_est_attaque_pas_tombstone(tmp_path):
    km = _km(tmp_path)
    enc = encrypt.encrypt_event(_ev(source="human:a"), "slot:a", km)
    tampered = enc.model_copy(update={"source": "human:b"})       # cles PRESENTES, en-tete modifie
    with pytest.raises(encrypt.IntegrityError):
        encrypt.decrypt_or_tombstone(tampered, km)


# ---- test 8 : rotation master + slot = RE-WRAP seul, aucune ligne reecrite ----
def test_8_rotation_est_rewrap_only(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    e = _append_encrypted(journal, "slot:a", km)
    line_before = _raw_line(journal, e.id)
    km.rotate_master(crypto.gen_key())
    km.rotate_slot("slot:a")
    assert _raw_line(journal, e.id) == line_before               # journal INTACT
    d = encrypt.decrypt_or_tombstone(read_events(journal)[0], km)
    assert d.title == "titre secret"                             # toujours lisible apres rotation


# ---- test 3 : la chaine de hachage reste valide apres shred (la ligne ne bouge pas) ----
def test_3_chaine_invariante_au_shred(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    e = _append_encrypted(journal, "slot:a", km)
    integrity.seal(journal)                                      # sceau AVANT effacement (count=1)
    old_seals = integrity.load_seals(journal)
    erase.erase("slot:a", km, journal, EmbeddingStore(tmp_path / "emb.jsonl"), read_events(journal))
    lines = integrity._lines(journal)
    assert integrity.verify(lines, old_seals)["ok"]             # sceaux anterieurs TOUJOURS valides
    assert len(lines) == 2                                       # tete avancee de l'event erasure


# ---- test 4 : shred irreversible -> tombstone, en-tetes conserves ----
def test_4_shred_irreversible_tombstone(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    e = _append_encrypted(journal, "slot:a", km)
    erase.erase("slot:a", km, journal, EmbeddingStore(tmp_path / "emb.jsonl"), read_events(journal))
    t = encrypt.decrypt_or_tombstone(read_events(journal)[0], km)
    assert t.title == "[efface]" and t.source == e.source and t.id == e.id


# ---- test 5 : censure detectee (cle detruite SANS event erasure) ----
def test_5_censure_detectee(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    _append_encrypted(journal, "slot:a", km)
    km.destroy("slot:a")                                         # detruite hors procedure -> pas d'intent
    r = integrity.verify_keyring(read_events(journal), km, EmbeddingStore(tmp_path / "emb.jsonl"))
    assert "slot:a" in r["unauthorized"] and not r["ok"]


# ---- test 6 : fausse conformite (intent journalise mais crash avant destroy) + reprise ----
def test_6_fausse_conformite_puis_reprise(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    _append_encrypted(journal, "slot:a", km)
    append_events(journal, [AetherEvent(type=EventType.ERASURE, title="erasure",
                  source="human:operator", data={"targets": ["slot:a"]})])   # intent... puis CRASH avant destroy
    emb = EmbeddingStore(tmp_path / "emb.jsonl")
    r = integrity.verify_keyring(read_events(journal), km, emb)
    assert "slot:a" in r["incomplete"] and not r["ok"]
    erase.erase_resume(read_events(journal), km, emb)            # reprise idempotente
    assert integrity.verify_keyring(read_events(journal), km, emb)["ok"]


# ---- test 7 : purge d'index, pas de resurrection au rebuild ----
def test_7_purge_projection_pas_de_resurrection(tmp_path):
    km = _km(tmp_path); journal = tmp_path / "j.jsonl"
    e = _append_encrypted(journal, "slot:a", km)
    emb = EmbeddingStore(tmp_path / "emb.jsonl"); emb.add({e.id: [0.1] * 8})
    assert emb.contains(e.id)
    erase.erase("slot:a", km, journal, emb, read_events(journal))
    assert not emb.contains(e.id)                               # vecteur purge (fuite ②bis fermee)
    assert e.id in [x.id for x in read_events(journal)]         # l'event existe toujours (append-only)
    # rebuild : le tombstone est detectable -> exclu du re-embed, donc pas de resurrection
    back = encrypt.decrypt_or_tombstone(read_events(journal)[0], km)
    assert back.data.get("erased") is True
