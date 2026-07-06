"""Journal : robustesse concurrence (Fable 5) - verrou d'ecriture + lecture tolerante.
Le round-trip append/read tient ; une derniere ligne partielle est ignoree ; une corruption au
milieu leve (jamais masquee)."""
from datetime import datetime, timezone

import pytest

from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(text):
    return AetherEvent(type=EventType.NOTE, title="n", description=text, source="project:demo",
                       observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                       data={"text": text, "session_id": "s", "turn_id": "t"})


def test_append_read_roundtrip_sous_verrou(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("a"), _ev("b")])
    append_events(str(jp), [_ev("c")])
    evs = read_events(str(jp))
    assert [e.data["text"] for e in evs] == ["a", "b", "c"]
    assert not (tmp_path / "j.jsonl.lock").exists()          # verrou libere


def test_read_tolere_derniere_ligne_partielle(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("ok1"), _ev("ok2")])
    with jp.open("a", encoding="utf-8") as f:
        f.write('{"type": "note", "descr')                   # ecriture en cours -> ligne tronquee
    evs = read_events(str(jp))
    assert [e.data["text"] for e in evs] == ["ok1", "ok2"]   # les valides, la partielle ignoree


def test_read_leve_sur_corruption_au_milieu(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("ok1")])
    with jp.open("a", encoding="utf-8") as f:
        f.write("ligne corrompue au milieu\n")
    append_events(str(jp), [_ev("ok2")])                     # une ligne valide APRES -> la corrompue n'est plus la derniere
    with pytest.raises(Exception):
        read_events(str(jp))
