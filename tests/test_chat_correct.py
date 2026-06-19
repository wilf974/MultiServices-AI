"""Boucle C3 — commande /correct : journaliser une correction qui marque les souvenirs revises.

Contrat : make_correction produit un evenement CORRECTION (C2 source, C3 valid_from, session) ;
une fois journalise, les souvenirs ANTERIEURS de la session deviennent `superseded` dans recall.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.chat import make_correction
from multiservice.events import AetherEvent, EventType
from multiservice.memory import recall

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)
SID = "s1"


def test_make_correction_porte_c2_c3():
    ev = make_correction("en fait 16 connexions", SID, now=T0)
    assert ev.type == EventType.CORRECTION
    assert ev.source == "user:local"           # C2
    assert ev.valid_from is not None             # C3
    assert ev.data["session_id"] == SID and ev.data["text"] == "en fait 16 connexions"


def test_correction_rend_le_souvenir_superseded():
    comp = AetherEvent(type=EventType.COMPLETION, title="x", description="le pool tient 8 connexions",
                       source="llm:eve", observed_at=T0,
                       data={"text": "le pool tient 8 connexions", "turn_id": "t1", "session_id": SID})
    corr = make_correction("en fait 16 connexions", SID, now=T0 + timedelta(minutes=5))
    hit = [h for h in recall([comp, corr], "pool connexions") if h["type"] == "completion"][0]
    assert hit["superseded"] is True
    assert corr.id in hit["corrected_by"]


def test_correction_n_affecte_pas_les_autres_sessions():
    comp = AetherEvent(type=EventType.COMPLETION, title="x", description="le pool tient 8 connexions",
                       source="llm:eve", observed_at=T0,
                       data={"text": "le pool tient 8 connexions", "turn_id": "t1", "session_id": "autre"})
    corr = make_correction("en fait 16", SID, now=T0 + timedelta(minutes=5))
    hit = [h for h in recall([comp, corr], "pool connexions") if h["type"] == "completion"][0]
    assert hit["superseded"] is False            # correction d'une AUTRE session
