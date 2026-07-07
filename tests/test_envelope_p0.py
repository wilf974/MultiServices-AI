"""P0 chiffrement — envelope.py : PUR. Plaintext canonique, AAD (chaines seules), build/parse data.enc.
Garde ⑥ : l'AAD ne contient QUE des chaines [id,type,source] — jamais de datetime (byte-instable)."""
from datetime import datetime, timezone

from multiservice import envelope
from multiservice.events import AetherEvent, EventType


def _ev(**kw):
    d = dict(type=EventType.NOTE, title="titre secret", description="desc secrete",
             source="human:local", data={"x": 1, "y": "z"})
    d.update(kw)
    return AetherEvent(**d)


def test_plaintext_exclut_enc_et_roundtrip():
    e = _ev()
    pt = envelope.canonical_plaintext(e)
    e2 = envelope.merge_plaintext(_ev(title="", description="", data={}), pt)
    assert (e2.title, e2.description, e2.data) == ("titre secret", "desc secrete", {"x": 1, "y": "z"})


def test_plaintext_ignore_le_champ_enc():
    e = _ev(data={"x": 1, "enc": {"ne": "doit pas fuiter"}})
    pt = envelope.canonical_plaintext(e)
    assert b"ne doit pas fuiter" not in pt and b"enc" not in pt   # 'enc' retire du plaintext


def test_aad_chaines_seules_sans_datetime():
    # valid_from a microsecondes non-nulles : mordrait un AAD qui re-serialiserait un datetime (garde ⑥)
    e = _ev(observed_at=datetime(2026, 7, 7, 12, 0, 0, 123456, tzinfo=timezone.utc))
    aad = envelope.canonical_aad(e)
    assert e.id.encode() in aad and b"human:local" in aad and b"note" in aad
    assert b"valid_from" not in aad and b"2026-07-07" not in aad   # AUCUN datetime dans l'AAD


def test_is_encrypted():
    plain = _ev()
    assert not envelope.is_encrypted(plain)
    line = plain.model_copy(update=envelope.build_line_fields(plain, "slot:a", b"n" * 12, b"ciphertext"))
    assert envelope.is_encrypted(line)
    assert line.title == "" and line.description == "" and line.data["enc"]["slot"] == "slot:a"
