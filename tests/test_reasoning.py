"""Memory Intelligence #2 — typage causal : reasoning_chain.

Contrat : le fil de raisonnement d'une session, ordonne (hypothese -> observation -> decision ->
correction -> validation), avec etapes presentes/manquantes (ex: decision sans validation), et la
fraicheur C3 sur chaque pas. PUR, lecture seule.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import reasoning_chain

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
S = "dunkbot-moteur"


def _ev(typ, text, mins, sid=S):
    return AetherEvent(type=typ, title=typ.value, description=text, source="project:local",
                       observed_at=T0 + timedelta(minutes=mins),
                       data={"text": text, "session_id": sid, "turn_id": f"t{mins}"})


def test_fil_ordonne_et_type():
    evs = [
        _ev(EventType.VALIDATION, "le bras tient la poele pleine", 30),
        _ev(EventType.HYPOTHESIS, "le NEMA-17 manque de couple", 0),
        _ev(EventType.DECISION, "passer au servo MG996R", 20),
        _ev(EventType.OBSERVATION, "le bras cale sous le poids", 10),
    ]
    out = reasoning_chain(evs, S)
    assert [s["stage"] for s in out["steps"]] == ["hypothesis", "observation", "decision", "validation"]
    assert out["stages_missing"] == ["correction"]
    assert out["count"] == 4


def test_decision_sans_validation_est_signalee():
    evs = [
        _ev(EventType.HYPOTHESIS, "idee A", 0),
        _ev(EventType.HYPOTHESIS, "idee B", 1),
        _ev(EventType.DECISION, "on tente A", 5),
    ]
    out = reasoning_chain(evs, S)
    assert "validation" in out["stages_missing"]      # « 3 pistes, aucune validee »
    assert "hypothesis" in out["stages_present"] and "decision" in out["stages_present"]


def test_fraicheur_c3_sur_un_pas():
    evs = [
        _ev(EventType.DECISION, "moteur NEMA-17", 0),
        _ev(EventType.CORRECTION, "en fait servo MG996R", 10),
    ]
    out = reasoning_chain(evs, S)
    dec = [s for s in out["steps"] if s["stage"] == "decision"][0]
    assert dec["superseded"] is True                  # la decision a ete corrigee

def test_scope_session_et_purete():
    evs = [_ev(EventType.HYPOTHESIS, "ici", 0), _ev(EventType.DECISION, "ailleurs", 1, sid="autre")]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    out = reasoning_chain(evs, S)
    assert out["count"] == 1                           # l'event d'une autre session est ignore
    assert [e.model_dump() for e in evs] == snap       # pur
