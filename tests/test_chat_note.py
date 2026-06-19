"""Feature note proposee par l'agent : /note -> make_note (human-gated, MCP reste lecture seule).

Contrat : make_note produit un evenement NOTE (C2 source=agent:claude, C3 valid_from) ; une fois
journalise (par l'humain via /note), il est recallable comme tout souvenir.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.chat import make_note
from multiservice.events import EventType
from multiservice.memory import recall

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def test_make_note_porte_provenance_agent():
    ev = make_note("archi : pools ODBC par voie, timeout dur, jamais de gel", "s1", now=T0)
    assert ev.type == EventType.NOTE
    assert ev.source == "agent:claude"           # C2 : provenance honnete (contenu = agent)
    assert ev.valid_from is not None             # C3
    assert ev.data["text"].startswith("archi")


def test_note_devient_recallable():
    ev = make_note("le pool ODBC tient huit connexions par voie", "s1", now=T0)
    hits = recall([ev], "pool ODBC connexions")
    assert len(hits) == 1 and hits[0]["source"] == "agent:claude"
