"""S14 - memoire lecture seule : recall (bi-temporel, lexical), why, briefing, purete."""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import recall, why, briefing_today

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _ev(t, text, at=T0, vt=None, turn="t1", typ=EventType.PROMPT, src="user:local"):
    return AetherEvent(type=typ, title="x", description=text, source=src,
                       observed_at=at, valid_to=vt, data={"text": text, "turn_id": turn})


def test_recall_lexical_et_topk():
    evs = [_ev("p", "connecteur odbc hfsql"), _ev("p", "meteo a paris"),
           _ev("p", "odbc et hfsql encore", at=T0 + timedelta(minutes=1))]
    r = recall(evs, "hfsql", k=10)
    assert len(r) == 2 and all("hfsql" in h["text"] for h in r)
    assert r[0]["valid_from"] >= r[1]["valid_from"]      # plus recent d'abord


def test_recall_bitemporel_as_of():
    evs = [_ev("p", "fait futur", at=T0 + timedelta(days=2))]
    assert recall(evs, "futur", as_of=T0) == []          # pas encore valide a as_of
    cloture = [_ev("p", "fait clos", at=T0, vt=T0 + timedelta(hours=1))]
    assert recall(cloture, "clos", as_of=T0 + timedelta(hours=2)) == []  # clos (C3)
    assert len(recall(cloture, "clos", as_of=T0 + timedelta(minutes=30))) == 1


def test_why_ordonne_les_evts_du_tour():
    evs = [_ev("p", "prompt", turn="tA"),
           _ev("p", "reponse", turn="tA", typ=EventType.COMPLETION, src="llm:eve"),
           _ev("p", "autre tour", turn="tB")]
    w = why(evs, "tA")
    assert len(w) == 2 and {x["type"] for x in w} == {"prompt", "completion"}


def test_briefing_today_lecture_seule():
    evs = [_ev("p", "x", at=datetime.now(timezone.utc))]
    before = [e.id for e in evs]
    b = briefing_today(evs)
    assert "date" in b and "input_tokens" in b
    assert [e.id for e in evs] == before                 # rien mute


def test_mcp_server_import_paresseux(monkeypatch):
    """DETERMINISTE quel que soit l'environnement : on MASQUE le SDK `mcp` (sys.modules=None)
    au lieu de supposer qu'il n'est pas installe (le test cassait des que `mcp` etait present
    sur le poste, observe le 02/07/2026). L'import doit rester paresseux : le module
    s'importe sans SDK, l'erreur n'arrive qu'a build_server()."""
    import sys
    import pytest
    from multiservice.mcp_server import build_server
    monkeypatch.setitem(sys.modules, "mcp", None)
    monkeypatch.setitem(sys.modules, "mcp.server", None)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", None)
    with pytest.raises((ImportError, ModuleNotFoundError)):
        build_server()                                   # SDK masque -> erreur claire


def test_recall_multimots_classe_par_pertinence():
    evs = [
        _ev("p", "odbc seulement ici"),
        _ev("p", "odbc connexion reset thread reunis", at=T0 + timedelta(minutes=1)),
        _ev("p", "connexion reset", at=T0 + timedelta(minutes=2)),
    ]
    r = recall(evs, "odbc connexion reset thread", k=10)
    assert len(r) == 3
    assert "thread" in r[0]["text"]
    assert r[0]["score"] > r[1]["score"] >= r[2]["score"]


def test_recall_multimots_ne_renvoie_plus_zero():
    evs = [_ev("p", "reinitialisation de la connexion odbc sur un thread bloque")]
    assert len(recall(evs, "odbc connexion reset thread", k=5)) == 1


def test_recall_accent_insensible():
    evs = [_ev("p", "probleme de reseau et de creation")]
    assert len(recall(evs, "reseau creation", k=5)) == 1


def test_recall_phrase_exacte_boostee():
    evs = [
        _ev("p", "odbc puis plus loin connexion", at=T0),
        _ev("p", "odbc connexion directe", at=T0 + timedelta(minutes=1)),
    ]
    r = recall(evs, "odbc connexion", k=5)
    assert "directe" in r[0]["text"]


def test_replay_session_ordonne_et_complet():
    from multiservice.memory import replay_session
    evs = [
        _ev("p", "t2", at=T0 + timedelta(minutes=2), turn="b"),
        _ev("p", "t1", at=T0, turn="a"),
        _ev("p", "autre session", at=T0, turn="z"),
    ]
    # forcer le session_id : _ev met turn_id mais pas session_id -> on patche data
    for e, sid in zip(evs, ["S", "S", "OTHER"]):
        e.data["session_id"] = sid
    r = replay_session(evs, "S")
    assert len(r) == 2
    assert r[0]["text"] == "t1" and r[1]["text"] == "t2"   # ordre chronologique
    assert all(x["turn_id"] in ("a", "b") for x in r)


def test_replay_session_inconnue_vide():
    from multiservice.memory import replay_session
    assert replay_session([], "nexiste-pas") == []


def test_ordre_metier_prompt_avant_completion():
    # meme horodatage : prompt doit venir AVANT completion, token_usage en dernier
    from multiservice.memory import replay_session
    evs = []
    e_comp = _ev("p", "rep", turn="t1", typ=EventType.COMPLETION, src="llm:eve")
    e_prompt = _ev("p", "question", turn="t1", typ=EventType.PROMPT)
    e_tok = _ev("p", "tok", turn="t1", typ=EventType.TOKEN_USAGE, src="meter")
    for e in (e_comp, e_prompt, e_tok):
        e.data["session_id"] = "S"
    r = replay_session([e_comp, e_prompt, e_tok], "S")
    assert [x["type"] for x in r] == ["prompt", "completion", "token_usage"]


def test_recall_filtre_type():
    evs = [
        _ev("p", "odbc question", typ=EventType.PROMPT),
        _ev("p", "odbc reponse", typ=EventType.COMPLETION, src="llm:eve"),
    ]
    only_prompts = recall(evs, "odbc", type_="prompt")
    assert only_prompts and all(h["type"] == "prompt" for h in only_prompts)


def test_recall_filtre_source():
    evs = [
        _ev("p", "odbc question", typ=EventType.PROMPT, src="user:local"),
        _ev("p", "odbc reponse", typ=EventType.COMPLETION, src="llm:eve"),
    ]
    only_llm = recall(evs, "odbc", source_prefix="llm")
    assert only_llm and all(h["source"].startswith("llm") for h in only_llm)
