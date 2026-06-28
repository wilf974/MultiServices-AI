"""EmbeddedGGUF (llama-cpp) - support du function calling : passe `tools` a create_chat_completion
et parse les `tool_calls` (format OpenAI, arguments en chaine JSON) -> Completion.tool_calls.
On bypass __init__ (pas de chargement de modele) en injectant un faux _llm.
"""
from multiservice.backends import Completion, EmbeddedGGUF


class _FakeLlm:
    def __init__(self, response):
        self._resp = response
        self.last_kwargs = None

    def create_chat_completion(self, **kwargs):
        self.last_kwargs = kwargs
        return self._resp


def _mk(response):
    be = EmbeddedGGUF.__new__(EmbeddedGGUF)   # skip __init__ (pas de .gguf a charger)
    be.model_id = "gguf-test"
    be._llm = _FakeLlm(response)
    return be


def test_gguf_parse_tool_calls():
    be = _mk({"choices": [{"message": {"content": "",
              "tool_calls": [{"function": {"name": "recall", "arguments": "{\"query\": \"cache\"}"}}]}}],
              "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    c = be.chat([{"role": "user", "content": "?"}],
                tools=[{"type": "function", "function": {"name": "recall", "parameters": {}}}])
    assert isinstance(c, Completion)
    assert be._llm.last_kwargs.get("tools")          # tools bien transmis a llama-cpp
    assert c.tool_calls[0]["function"]["name"] == "recall"
    assert c.tool_calls[0]["function"]["arguments"] == {"query": "cache"}   # chaine JSON -> dict


def test_gguf_reponse_simple_sans_tools():
    be = _mk({"choices": [{"message": {"content": "Bonjour."}}],
              "usage": {"prompt_tokens": 4, "completion_tokens": 3}})
    c = be.chat([{"role": "user", "content": "salut"}])
    assert c.text == "Bonjour." and not c.tool_calls
