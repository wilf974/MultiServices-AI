"""Boucle agentique de memoire : le MODELE appelle les outils lui-meme.
modele -> tool_calls -> l'hote execute (read/write) -> resultat renvoye -> le modele conclut.
Chaque appel d'outil est journalise (TOOL_CALL + TOOL_RESULT) -> auditable. Backend scripte (no reseau).
"""
from datetime import datetime, timezone

from multiservice.agent import AgentResult, run_with_memory_tools
from multiservice.backends import Completion
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _seed(path):
    ev = AetherEvent(type=EventType.NOTE, title="note",
                     description="Le module de cache NIMBUS-7 cible 42 ms",
                     source="agent:claude", observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                     data={"text": "Le module de cache NIMBUS-7 cible 42 ms",
                           "session_id": "s1", "turn_id": "t1"})
    append_events(str(path), [ev])
    return str(path)


class ScriptBackend:
    """Rejoue une sequence de Completion. Accepte (et ignore) tools/on_token."""

    def __init__(self, script):
        self.model_id = "qwen3.6"
        self.count_source = "local_tokenizer"
        self._script = list(script)
        self.calls = 0

    def chat(self, messages, on_token=None, tools=None):
        c = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        if on_token and c.text:
            on_token(c.text)
        return c

    def generate(self, prompt):
        return self.chat([{"role": "user", "content": prompt}])


def _tc(name, **args):
    return [{"function": {"name": name, "arguments": args}}]


def test_modele_appelle_recall_puis_repond(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    be = ScriptBackend([
        Completion("", "qwen3.6", 5, 0, tool_calls=_tc("recall", query="NIMBUS")),
        Completion("D'apres la memoire : NIMBUS-7, 42 ms.", "qwen3.6", 6, 9),
    ])
    res = run_with_memory_tools(be, [{"role": "user", "content": "c'est quoi NIMBUS ?"}], jp, "sess")
    assert isinstance(res, AgentResult)
    assert "NIMBUS-7" in res.completion.text
    evs = read_events(jp)
    assert any(e.type == EventType.TOOL_CALL and e.data.get("tool") == "recall" for e in evs)
    assert any(e.type == EventType.TOOL_RESULT and e.data.get("tool") == "recall"
               and e.data.get("ok") is True for e in evs)


def test_modele_remember_ecrit_project_ollama(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    be = ScriptBackend([
        Completion("", "qwen3.6", 5, 0,
                   tool_calls=_tc("remember", text="le cache vise 42 ms", kind="observation")),
        Completion("C'est note.", "qwen3.6", 4, 3),
    ])
    run_with_memory_tools(be, [{"role": "user", "content": "retiens ca"}], jp, "sess")
    notes = [e for e in read_events(jp) if e.type == EventType.NOTE and e.source == "project:ollama"]
    assert any("42 ms" in (e.data.get("text") or "") for e in notes)


def test_max_steps_borne_la_boucle(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    be = ScriptBackend([Completion("", "qwen3.6", 1, 0, tool_calls=_tc("recall", query="x"))])  # boucle infinie potentielle
    run_with_memory_tools(be, [{"role": "user", "content": "boucle"}], jp, "sess", max_steps=3)
    calls = [e for e in read_events(jp) if e.type == EventType.TOOL_CALL]
    assert len(calls) <= 3


def test_outil_inconnu_renvoye_au_modele(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    be = ScriptBackend([
        Completion("", "qwen3.6", 1, 0, tool_calls=_tc("nope")),
        Completion("desole, je n'ai pas pu.", "qwen3.6", 1, 4),
    ])
    run_with_memory_tools(be, [{"role": "user", "content": "x"}], jp, "sess")
    tr = [e for e in read_events(jp) if e.type == EventType.TOOL_RESULT]
    assert any(e.data.get("ok") is False for e in tr)
