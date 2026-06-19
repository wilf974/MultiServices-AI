"""Feature « quoi de neuf » : memory.recent (fenetre temporelle, point d'entree de reprise).

Contrat : ne garde que les evenements de la fenetre `days`, du plus recent au plus ancien ;
separe decisions et corrections ; `latest` = k textuels recents. PUR, lecture seule.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import recent

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, at):
    return AetherEvent(type=typ, title="x", description=text, source="user:wilfred",
                       observed_at=at, data={"text": text, "turn_id": "t", "session_id": "s"})


def _journal():
    return [
        _ev(EventType.PROMPT, "hier", NOW - timedelta(days=1)),
        _ev(EventType.DECISION, "decision recente", NOW - timedelta(hours=2)),
        _ev(EventType.CORRECTION, "correction recente", NOW - timedelta(hours=1)),
        _ev(EventType.PROMPT, "vieux truc", NOW - timedelta(days=30)),
    ]


def test_fenetre_exclut_l_ancien():
    r = recent(_journal(), days=7, now=NOW)
    assert r["count"] == 3                              # le vieux de 30j est exclu
    assert not any("vieux" in x["text"] for x in r["latest"])


def test_separe_decisions_et_corrections():
    r = recent(_journal(), days=7, now=NOW)
    assert len(r["decisions"]) == 1 and "decision" in r["decisions"][0]["text"]
    assert len(r["corrections"]) == 1 and "correction" in r["corrections"][0]["text"]


def test_latest_du_plus_recent_au_plus_ancien():
    r = recent(_journal(), days=7, now=NOW)
    vfs = [x["valid_from"] for x in r["latest"]]
    assert vfs == sorted(vfs, reverse=True)            # plus recent d'abord


def test_fenetre_vide_est_sure():
    r = recent(_journal(), days=0, now=NOW)
    assert r["count"] == 0 and r["latest"] == []
