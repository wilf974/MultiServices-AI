"""Souverainete cloud + outils memoire : les outils memoire ne sont exposes QUE pour un tour LOCAL.

Regle stricte : si le tour est lance en mode CLOUD (routage cloud), AUCUN outil memoire (ni recall
ni remember), AUCUN TOOL_CALL/TOOL_RESULT journalise -- meme si le tour fallback local ensuite.
Le sensible et la memoire ne partent jamais au cloud.
"""
from datetime import datetime, timezone

from multiservice import chat
from multiservice.backends import BackendError, Completion
from multiservice.chat import TurnResult, serve_turn, should_expose_memory_tools
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events
from multiservice.routing import Router


def _seed(path):
    ev = AetherEvent(type=EventType.NOTE, title="note", description="NIMBUS-7 cible 42 ms",
                     source="agent:claude", observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                     data={"text": "NIMBUS-7 cible 42 ms", "session_id": "s1", "turn_id": "t1"})
    append_events(str(path), [ev])
    return str(path)


class LocalToolBackend:
    """Local outillable : emet un tool_call recall puis une reponse finale."""

    model_id = "qwen3.6"
    count_source = "local_tokenizer"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, on_token=None, tools=None):
        self.calls += 1
        if self.calls == 1:
            return Completion("", "qwen3.6", 2, 0,
                              tool_calls=[{"function": {"name": "recall", "arguments": {"query": "NIMBUS"}}}])
        return Completion("NIMBUS-7, 42 ms.", "qwen3.6", 3, 5)


class CloudBackend:
    model_id = "sonar"
    count_source = "provider_usage"

    def __init__(self, fail=False):
        self._fail = fail

    def chat(self, messages, on_token=None):
        if self._fail:
            raise BackendError("missing_api_key", "pas de cle")
        return Completion("[sonar] reponse cloud", "sonar", 4, 6)


class PlainLocal:
    model_id = "qwen3.6"
    count_source = "local_tokenizer"

    def chat(self, messages, on_token=None):
        return Completion("[local] reponse", "qwen3.6", 2, 3)


def _has_tool_events(jp):
    return any(e.type in (EventType.TOOL_CALL, EventType.TOOL_RESULT) for e in read_events(jp))


# --- la garde pure ---

def test_should_expose_only_local():
    assert should_expose_memory_tools("local", True) is True
    assert should_expose_memory_tools("cloud", True) is False
    assert should_expose_memory_tools("local", False) is False
    assert should_expose_memory_tools("cloud", False) is False


# --- serve_turn : tour LOCAL + memory-tools -> outils exposes ---

def test_local_route_outils_presents(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=LocalToolBackend(), cloud=CloudBackend())
    tr = serve_turn(router, "c'est quoi NIMBUS ?", [{"role": "user", "content": "c'est quoi NIMBUS ?"}],
                    cloud_ok=False, memory_tools=True, journal_path=jp, session_id="sess")
    assert isinstance(tr, TurnResult)
    assert tr.used_memory_tools is True
    assert tr.routing["routed_to"] == "local"
    assert _has_tool_events(jp)                         # le modele a appele un outil -> journalise


# --- serve_turn : tour CLOUD + memory-tools -> AUCUN outil ---

def test_cloud_route_aucun_outil(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=LocalToolBackend(), cloud=CloudBackend())
    tr = serve_turn(router, "resume l'archi", [{"role": "user", "content": "resume l'archi"}],
                    cloud_ok=True, memory_tools=True, journal_path=jp, session_id="sess")
    assert tr.used_memory_tools is False
    assert tr.routing["routed_to"] == "cloud"
    assert tr.completion.model_id == "sonar"
    assert not _has_tool_events(jp)                     # aucun TOOL_CALL/TOOL_RESULT cote cloud


def test_cloud_route_aucun_remember(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=LocalToolBackend(), cloud=CloudBackend())
    serve_turn(router, "memorise X", [{"role": "user", "content": "memorise X"}],
               cloud_ok=True, memory_tools=True, journal_path=jp, session_id="sess")
    assert not any(e.type == EventType.NOTE and e.source == "project:ollama" for e in read_events(jp))


# --- fallback strict : tour lance cloud, cloud KO -> fallback local SANS outils ---

def test_cloud_fallback_local_sans_outils(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=PlainLocal(), cloud=CloudBackend(fail=True))
    tr = serve_turn(router, "resume l'archi", [{"role": "user", "content": "resume l'archi"}],
                    cloud_ok=True, memory_tools=True, journal_path=jp, session_id="sess")
    assert tr.used_memory_tools is False
    assert tr.completion.model_id == "qwen3.6"          # le local a servi (fallback)
    assert tr.routing["routing_reason"] == "cloud_error_fallback_local"
    assert not _has_tool_events(jp)                     # toujours aucun outil memoire dans cette passe
