"""Memoire agentique - registre d'outils LECTURE SEULE expose au modele (Ollama tool calling).

Le modele appelle lui-meme `recall`/`why`/... ; l'hote execute (read-only) et renvoie le resultat.
Aucun outil n'ecrit le journal (D5). Les specs sont au format function-calling Ollama/OpenAI.
"""
from datetime import datetime, timezone

import pytest

from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events
from multiservice.memory_tools import ToolError, build_tool_specs, run_tool


def _seed(path):
    ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evs = [
        AetherEvent(type=EventType.NOTE, title="note",
                    description="Le module de cache NIMBUS-7 cible 42 ms",
                    source="agent:claude", observed_at=ts,
                    data={"text": "Le module de cache NIMBUS-7 cible 42 ms",
                          "session_id": "s1", "turn_id": "t1"}),
        AetherEvent(type=EventType.PROMPT, title="prompt", description="question sur le cache",
                    source="user:local", observed_at=ts,
                    data={"text": "question sur le cache", "session_id": "s1", "turn_id": "t1"}),
    ]
    append_events(str(path), evs)
    return str(path)


def test_specs_panel_complet():
    names = {t["function"]["name"] for t in build_tool_specs()}
    assert {"recall", "recall_semantic", "recent", "why", "replay", "brief", "lessons"} <= names
    for t in build_tool_specs():                       # forme function-calling valide
        assert t["type"] == "function"
        fn = t["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object" and "properties" in fn["parameters"]


def test_run_recall_trouve_le_fait(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("recall", {"query": "NIMBUS cache"}, jp)
    assert isinstance(res, list)
    assert "NIMBUS-7" in __import__("json").dumps(res, ensure_ascii=False)


def test_run_why_par_turn(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("why", {"turn_id": "t1"}, jp)
    assert isinstance(res, list) and len(res) >= 1


def test_run_recent_et_lessons_et_brief(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    assert run_tool("recent", {"days": 3650}, jp)["days"] == 3650
    assert isinstance(run_tool("lessons", {}, jp), dict)
    assert isinstance(run_tool("brief", {"query": "cache"}, jp), dict)


def test_run_replay_session(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("replay", {"session_id": "s1"}, jp)
    assert res is not None


def test_recall_semantic_sans_store_se_replie(tmp_path):
    # pas d'embedder/store fourni -> repli lexical propre, jamais de crash.
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("recall_semantic", {"query": "NIMBUS"}, jp)
    assert isinstance(res, list)


def test_outil_inconnu_erreur_structuree(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    with pytest.raises(ToolError) as ei:
        run_tool("DROP TABLE", {}, jp)
    assert ei.value.kind == "unknown_tool"


# --- outil d'ECRITURE garde : remember -> project:ollama (append-only, non-autoritaire) ---

def _read(jp):
    from multiservice.journal import read_events
    return read_events(jp)


def test_specs_contient_remember():
    names = {t["function"]["name"] for t in build_tool_specs()}
    assert "remember" in names


def test_remember_ecrit_une_note_source_ollama(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("remember", {"text": "appris: le seuil semcache est 0.95", "kind": "observation"}, jp)
    assert isinstance(res, dict) and res.get("source") == "project:ollama" and res.get("id")
    notes = [e for e in _read(jp) if e.type == EventType.NOTE and e.source == "project:ollama"]
    assert any("semcache" in (e.data.get("text") or "") for e in notes)
    # recallable ensuite
    assert "semcache" in __import__("json").dumps(run_tool("recall", {"query": "semcache seuil"}, jp), ensure_ascii=False)


def test_remember_source_ne_peut_pas_etre_usurpee(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    res = run_tool("remember", {"text": "x", "source": "project:maison", "kind": "note"}, jp)
    assert res["source"] == "project:ollama"      # source FORCEE, jamais celle passee par le modele


def test_remember_kind_autoritaire_refuse(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    for k in ("decision", "validation", "correction"):
        with pytest.raises(ToolError) as ei:
            run_tool("remember", {"text": "je decide X", "kind": k}, jp)
        assert ei.value.kind == "forbidden_kind"


def test_remember_text_requis(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    with pytest.raises(ToolError) as ei:
        run_tool("remember", {"kind": "note"}, jp)
    assert ei.value.kind == "bad_args"


def test_remember_dedup(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    run_tool("remember", {"text": "fait identique a memoriser"}, jp)
    n1 = len([e for e in _read(jp) if e.type == EventType.NOTE and e.source == "project:ollama"])
    run_tool("remember", {"text": "fait identique a memoriser"}, jp)   # doublon -> non re-ecrit
    n2 = len([e for e in _read(jp) if e.type == EventType.NOTE and e.source == "project:ollama"])
    assert n2 == n1
