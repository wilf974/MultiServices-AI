"""Memory Intelligence #1 — lessons_learned : lecons tirees des corrections C3.

Contrat : une lecon = une correction + les faits anterieurs de SA session qu'elle perime ;
`still_standing` = les decisions encore valides (non corrigees). PUR, lecture seule ;
VIDE tant qu'aucune correction (calibre sur l'observe, pas invente).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import lessons_learned

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid, src="project:wilfred"):
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def test_vide_sans_correction():
    evs = [_ev(EventType.DECISION, "Licence MIT", T0, "licence")]
    out = lessons_learned(evs)
    assert out["counts"]["lessons"] == 0
    assert out["counts"]["still_standing"] == 1       # la decision tient (non corrigee)


def test_lecon_pointe_la_decision_perimee():
    evs = [
        _ev(EventType.DECISION, "Licence MIT", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0 (brevet)", T0 + timedelta(hours=1), "licence"),
        _ev(EventType.DECISION, "MCP en lecture seule", T0, "constitution"),   # non corrigee
    ]
    out = lessons_learned(evs)
    assert out["counts"]["lessons"] == 1
    lesson = out["lessons"][0]
    assert "Apache" in lesson["correction"]
    assert any("MIT" in s["text"] for s in lesson["superseded"])   # MIT abandonnee
    # la decision MIT n'est plus "still standing" ; la constitution oui
    sessions_still = {d["session"] for d in out["still_standing"]}
    assert "constitution" in sessions_still and "licence" not in sessions_still


def test_correction_scopee_a_sa_session():
    evs = [
        _ev(EventType.DECISION, "Decision A", T0, "sujet-A"),
        _ev(EventType.CORRECTION, "revise B", T0 + timedelta(hours=1), "sujet-B"),
    ]
    out = lessons_learned(evs)
    # la correction de sujet-B ne perime PAS la decision de sujet-A
    assert out["lessons"][0]["superseded"] == []
    assert any(d["session"] == "sujet-A" for d in out["still_standing"])


def test_lessons_est_pur():
    evs = [
        _ev(EventType.DECISION, "Licence MIT", T0, "licence"),
        _ev(EventType.CORRECTION, "Apache-2.0", T0 + timedelta(hours=1), "licence"),
    ]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    lessons_learned(evs)
    assert [e.model_dump() for e in evs] == snap
