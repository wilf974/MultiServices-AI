"""Amelioration MCP #3 — economie de SORTIE des outils (extraits + digest de session).

Contrat :
  - recall renvoie un EXTRAIT centre sur le terme trouve (pas un dump), texte court inchange ;
  - session_digest = 1 ligne compacte par tour (prompt/completion tronques + tokens), ordonnee.
PUR, lecture seule. Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import _snippet, recall, session_digest

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)


def test_snippet_centre_sur_le_terme_et_tronque():
    long = ("blabla intro " * 30) + " le pool ODBC tient huit connexions " + ("fin " * 30)
    s = _snippet(long, "ODBC connexions", width=120)
    assert len(s) <= 130
    assert "odbc" in s.lower()
    assert s.startswith("...") or s.endswith("...")     # ellipses sur texte long


def test_snippet_texte_court_inchange():
    assert _snippet("texte court", "court", width=200) == "texte court"


def test_recall_renvoie_un_extrait_pas_un_dump():
    long = ("aaa " * 50) + "connecteur hfsql special" + (" zzz" * 50)
    e = AetherEvent(type=EventType.COMPLETION, title="x", description=long, source="llm:eve",
                    observed_at=T0, data={"text": long, "turn_id": "t1", "session_id": "s1"})
    hit = recall([e], "hfsql special")[0]
    assert "hfsql" in hit["text"].lower()
    assert len(hit["text"]) < len(long)                  # economise : pas le dump entier


def _turn(tid, prompt, comp, nin, at):
    mk = lambda typ, txt, src, extra=None: AetherEvent(
        type=typ, title="x", description=txt, source=src, observed_at=at,
        data={"text": txt, "turn_id": tid, "session_id": "S", **(extra or {})})
    return [
        mk(EventType.PROMPT, prompt, "user:local"),
        mk(EventType.COMPLETION, comp, "llm:eve"),
        mk(EventType.TOKEN_USAGE, "tok", "meter", {"input_tokens": nin, "output_tokens": 10}),
    ]


def test_session_digest_compact_et_ordonne():
    evs = (_turn("b", "Q2", "R2", 200, T0 + timedelta(minutes=5))
           + _turn("a", "Q1", "R1", 100, T0))
    d = session_digest(evs, "S")
    assert d["turns"] == 2
    assert [r["turn_id"] for r in d["rows"]] == ["a", "b"]     # ordre chronologique
    assert d["rows"][0]["prompt"] == "Q1" and d["rows"][0]["in"] == 100
    assert d["rows"][1]["completion"] == "R2"


def test_session_digest_inconnue_vide():
    assert session_digest([], "rien")["turns"] == 0
