"""Amelioration MCP #2 — outil composE « brief sur un sujet ».

Contrat : un appel rend, pour un sujet, souvenirs + dEcisions (sEparEs, dEduplicquEs) +
ceux rEvisEs depuis (C3) + les sessions touchEes. PUR, lecture seule.

ValidE sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import topic_brief

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)


def _ev(type_, text, vf, sid, source="llm:eve", tid="t"):
    return AetherEvent(type=type_, title=type_.value, description=text, source=source,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": tid})


def _journal():
    return [
        _ev(EventType.DECISION, "Connecteur HFSQL via ODBC en lecture seule", T0, "s-dec",
            source="user:local"),
        _ev(EventType.COMPLETION, "le pool ODBC HFSQL tient 8 connexions", T0, "s1"),
        AetherEvent(type=EventType.CORRECTION, title="correction", description="en fait 16 ODBC",
                    source="user:local", observed_at=T0 + timedelta(minutes=5),
                    data={"text": "en fait 16 ODBC", "session_id": "s1", "turn_id": "t2"}),
        _ev(EventType.COMPLETION, "recette de tarte", T0, "s2"),   # hors sujet
    ]


def test_separe_souvenirs_et_decisions():
    b = topic_brief(_journal(), "ODBC HFSQL connexions", k=5)
    assert b["counts"]["decisions"] >= 1
    assert all(d["type"] == "decision" for d in b["decisions"])
    assert all(m["type"] != "decision" for m in b["memories"])   # pas de doublon dEcision
    assert not any("tarte" in m["text"] for m in b["memories"])   # le hors-sujet est ecartE


def test_signale_les_revises_c3():
    b = topic_brief(_journal(), "ODBC HFSQL connexions", k=5)
    assert any(h["superseded"] for h in b["revised"])
    assert b["counts"]["revised"] >= 1


def test_liste_les_sessions_pour_creuser():
    b = topic_brief(_journal(), "ODBC HFSQL connexions", k=5)
    assert "s1" in b["sessions"] and "s-dec" in b["sessions"]


def test_sujet_inconnu_donne_un_brief_vide():
    b = topic_brief(_journal(), "astrophysique quantique", k=5)
    assert b["counts"]["memories"] == 0 and b["counts"]["decisions"] == 0
    assert b["sessions"] == []
