"""Page de dev (local) - endpoint de chat : reponse JSON avec reponse + ACTIVITE MEMOIRE
(appels d'outils du modele) + provenance. Respecte la souverainete cloud+tools.
Backends factices (ni reseau, ni modele).
"""
from datetime import datetime, timezone

from multiservice.backends import Completion
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events
from multiservice.routing import Router
from multiservice.webchat import chat_response


def _seed(path):
    ev = AetherEvent(type=EventType.NOTE, title="note", description="NIMBUS-7 cible 42 ms",
                     source="agent:claude", observed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                     data={"text": "NIMBUS-7 cible 42 ms", "session_id": "s1", "turn_id": "t1"})
    append_events(str(path), [ev])
    return str(path)


class LocalToolBackend:
    model_id = "qwen3.6"
    count_source = "local_tokenizer"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, on_token=None, tools=None):
        self.calls += 1
        if self.calls == 1:
            return Completion("", "qwen3.6", 2, 0,
                              tool_calls=[{"function": {"name": "recall", "arguments": {"query": "NIMBUS"}}}])
        return Completion("D'apres la memoire : NIMBUS-7, 42 ms.", "qwen3.6", 3, 6)


class CloudBackend:
    model_id = "sonar"
    count_source = "provider_usage"

    def chat(self, messages, on_token=None):
        return Completion("[sonar] reponse cloud", "sonar", 4, 6)


def test_reponse_locale_expose_activite_memoire(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=LocalToolBackend(), cloud=CloudBackend())
    r = chat_response(router, "c'est quoi NIMBUS ?", journal_path=jp, session_id="sess",
                      memory_tools=True, cloud_ok=False)
    assert r["used_memory_tools"] is True
    assert r["routed_to"] == "local"
    assert "NIMBUS-7" in r["answer"]
    assert len(r["tool_calls"]) >= 1
    tc = r["tool_calls"][0]
    assert tc["tool"] == "recall" and tc["arguments"] == {"query": "NIMBUS"} and tc["ok"] is True


def test_is_gguf_detection():
    from multiservice.webchat import _is_gguf
    assert _is_gguf("C:/models/eve.gguf") and _is_gguf("a.GGUF")
    assert not _is_gguf("qwen3.6:latest") and not _is_gguf("")


def test_reponse_cloud_aucune_activite_memoire(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    router = Router(local=LocalToolBackend(), cloud=CloudBackend())
    r = chat_response(router, "resume l'archi", journal_path=jp, session_id="sess",
                      memory_tools=True, cloud_ok=True)
    assert r["used_memory_tools"] is False
    assert r["routed_to"] == "cloud"
    assert r["tool_calls"] == []                       # souverainete : aucun outil cote cloud
