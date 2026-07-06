"""OllamaBackend - support du function calling : payload `tools` (stream:false) + parsing des
`tool_calls` de la reponse. Pas de reseau : on monkeypatch urlopen.
"""
import io
import json

from multiservice import backends
from multiservice.backends import Completion, OllamaBackend


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def test_tools_envoie_stream_false_et_parse_tool_calls(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        resp = {
            "model": "qwen3.6",
            "message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": "recall",
                                                     "arguments": {"query": "cache"}}}]},
            "prompt_eval_count": 12, "eval_count": 4, "done": True,
        }
        return _FakeResp(json.dumps(resp).encode("utf-8"))

    monkeypatch.setattr(backends, "urlopen", fake_urlopen)
    be = OllamaBackend(model="qwen3.6")
    specs = [{"type": "function", "function": {"name": "recall", "parameters": {}}}]
    c = be.chat([{"role": "user", "content": "que sais-tu du cache ?"}], tools=specs)

    assert captured["body"]["stream"] is False           # tools -> non-streaming
    assert captured["body"]["tools"] == specs
    assert isinstance(c, Completion)
    assert c.tool_calls and c.tool_calls[0]["function"]["name"] == "recall"
    assert c.tool_calls[0]["function"]["arguments"] == {"query": "cache"}
    assert c.input_tokens == 12 and c.output_tokens == 4


def test_reponse_sans_tool_calls(monkeypatch):
    def fake_urlopen(req, timeout=None):
        resp = {"model": "qwen3.6",
                "message": {"role": "assistant", "content": "Le cache est a 42 ms."},
                "prompt_eval_count": 9, "eval_count": 7, "done": True}
        return _FakeResp(json.dumps(resp).encode("utf-8"))

    monkeypatch.setattr(backends, "urlopen", fake_urlopen)
    be = OllamaBackend(model="qwen3.6")
    c = be.chat([{"role": "user", "content": "le cache ?"}],
                tools=[{"type": "function", "function": {"name": "recall", "parameters": {}}}])
    assert c.text == "Le cache est a 42 ms."
    assert not c.tool_calls                              # None ou liste vide
