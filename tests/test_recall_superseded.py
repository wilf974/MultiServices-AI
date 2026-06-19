"""Amelioration MCP #1 — drapeau de fraicheur C3 sur recall (vu du cote agent).

Contrat : un hit signale s'il a ete CORRIGE plus tard dans la MEME session (`superseded` +
`corrected_by`), pour ne jamais citer une memoire revisee sans reserve. Lecture seule, pur.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import recall

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)
SID = "s1"


def _ev(type_, text, vf, sid=SID, tid="t"):
    return AetherEvent(type=type_, title=type_.value, description=text, source="llm:eve",
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": tid})


def test_hit_corrige_plus_tard_est_signale():
    evs = [
        _ev(EventType.COMPLETION, "le pool ODBC tient 8 connexions", T0),
        AetherEvent(type=EventType.CORRECTION, title="correction", description="en fait 16",
                    source="user:wilfred", observed_at=T0 + timedelta(minutes=10),
                    data={"text": "en fait 16", "session_id": SID, "turn_id": "t2"}),
    ]
    hit = [h for h in recall(evs, "pool ODBC connexions") if h["type"] == "completion"][0]
    assert hit["superseded"] is True
    assert len(hit["corrected_by"]) == 1


def test_hit_sans_correction_posterieure_est_frais():
    evs = [_ev(EventType.COMPLETION, "le pool ODBC tient 8 connexions", T0)]
    hit = recall(evs, "pool ODBC connexions")[0]
    assert hit["superseded"] is False
    assert hit["corrected_by"] == []


def test_correction_anterieure_ne_compte_pas():
    evs = [
        AetherEvent(type=EventType.CORRECTION, title="correction", description="vieux",
                    source="user:wilfred", observed_at=T0 - timedelta(minutes=10),
                    data={"text": "vieux", "session_id": SID, "turn_id": "t0"}),
        _ev(EventType.COMPLETION, "le pool ODBC tient 8 connexions", T0),
    ]
    hit = [h for h in recall(evs, "pool ODBC connexions") if h["type"] == "completion"][0]
    assert hit["superseded"] is False


def test_correction_autre_session_ne_compte_pas():
    evs = [
        _ev(EventType.COMPLETION, "le pool ODBC tient 8 connexions", T0),
        AetherEvent(type=EventType.CORRECTION, title="correction", description="ailleurs",
                    source="user:wilfred", observed_at=T0 + timedelta(minutes=10),
                    data={"text": "ailleurs", "session_id": "autre", "turn_id": "tx"}),
    ]
    hit = [h for h in recall(evs, "pool ODBC connexions") if h["type"] == "completion"][0]
    assert hit["superseded"] is False
