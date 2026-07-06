"""Tranche 1 - PerplexityBackend (cloud, OpenAI-compatible, stdlib urllib).

Contraintes : cle via env, erreurs STRUCTUREES, timeout explicite, count_source='provider_usage'.
Pas d'appel reseau reel : on monkeypatch urlopen.
"""
import io
import json

import pytest

from multiservice import backends
from multiservice.backends import BackendError, Completion, PerplexityBackend


def test_cle_absente_erreur_structuree():
    be = PerplexityBackend(api_key="")
    with pytest.raises(BackendError) as ei:
        be.generate("bonjour")
    assert ei.value.kind == "missing_api_key"


def test_count_source_est_provider_usage():
    assert PerplexityBackend(api_key="x").count_source == "provider_usage"


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def test_succes_mappe_completion_et_usage(monkeypatch):
    payload = {
        "model": "sonar",
        "choices": [{"message": {"content": "Bonjour !"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }

    def fake_urlopen(req, timeout=None):
        # Verifie l'en-tete d'auth construit par le backend.
        assert req.get_header("Authorization") == "Bearer test-key"
        return _FakeResp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(backends, "urlopen", fake_urlopen)
    be = PerplexityBackend(api_key="test-key", model="sonar")
    c = be.generate("salut")
    assert isinstance(c, Completion)
    assert c.text == "Bonjour !"
    assert c.model_id == "sonar"
    assert c.input_tokens == 11 and c.output_tokens == 7


def test_http_error_devient_backend_error(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(req, timeout=None):
        raise HTTPError(req.full_url, 401, "Unauthorized", hdrs=None,
                        fp=io.BytesIO(b'{"error":"unauthorized"}'))

    monkeypatch.setattr(backends, "urlopen", fake_urlopen)
    be = PerplexityBackend(api_key="bad")
    with pytest.raises(BackendError) as ei:
        be.generate("salut")
    assert ei.value.kind == "http_error" and ei.value.status == 401
