"""S13 - OllamaBackend : streaming NDJSON, on_token, journalisation (sans serveur)."""
import json

from multiservice import backends
from multiservice.chat import record_turn
from multiservice.events import EventType
from multiservice.journal import read_events


class _FakeStream:
    """Imite une reponse HTTP streamee : iterable de lignes NDJSON (bytes)."""
    def __init__(self, lines): self._lines = [l.encode("utf-8") for l in lines]
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(self._lines)


def _fake_urlopen(lines):
    def _f(req, timeout=None):
        return _FakeStream(lines)
    return _f


def _lines():
    return [
        json.dumps({"model": "qwen3.6", "message": {"content": "bon"}, "done": False}) + "\n",
        json.dumps({"message": {"content": "jour"}, "done": False}) + "\n",
        json.dumps({"done": True, "model": "qwen3.6", "prompt_eval_count": 12, "eval_count": 5}) + "\n",
    ]


def test_ollama_streaming_assemble_et_compte(monkeypatch):
    monkeypatch.setattr(backends, "urlopen", _fake_urlopen(_lines()))
    seen = []
    be = backends.OllamaBackend(model="qwen3.6")
    c = be.chat([{"role": "user", "content": "salut"}], on_token=seen.append)
    assert c.text == "bonjour"
    assert seen == ["bon", "jour"]                 # tokens diffuses en direct
    assert c.input_tokens == 12 and c.output_tokens == 5
    assert be.count_source == "local_tokenizer"


def test_ollama_journalise_un_tour(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "urlopen", _fake_urlopen(_lines()))
    be = backends.OllamaBackend(model="qwen3.6")
    comp = be.chat([{"role": "user", "content": "hi"}])
    jp = tmp_path / "journal-llm.jsonl"
    n = record_turn("hi", comp, be.count_source, jp, session_id="s1")
    assert n == 3
    back = read_events(jp)
    assert [e.type for e in back] == [EventType.PROMPT, EventType.COMPLETION, EventType.TOKEN_USAGE]
    assert back[2].data["count_source"] == "local_tokenizer"
    assert back[1].data["model_id"] == "qwen3.6"
