"""Outil `health` (kit LLM universel) : sante du substrat memoire, LECTURE SEULE, PUR.
Disponibilite (on a pu lire) + nombre d'evenements + dernier evenement + nombre de sources."""
from datetime import datetime, timezone, timedelta

from multiservice.events import AetherEvent, EventType
from multiservice.memory import health

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ev(text, vf, src="project:demo"):
    return AetherEvent(type=EventType.NOTE, title="note", description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": "s", "turn_id": "t"})


def test_health_resume_le_journal():
    evs = [_ev("a", T0, "project:demo"),
           _ev("b", T0 + timedelta(days=1), "project:bureau"),
           _ev("c", T0 + timedelta(days=2), "project:demo")]
    h = health(evs)
    assert h["available"] is True
    assert h["event_count"] == 3
    assert h["sources"] == 2                                # demo + bureau
    assert h["last_event_at"] == (T0 + timedelta(days=2)).isoformat()


def test_health_journal_vide():
    h = health([])
    assert h["available"] is True and h["event_count"] == 0
    assert h["last_event_at"] is None and h["sources"] == 0
