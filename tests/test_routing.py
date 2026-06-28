"""Tranche 1 - Router mince (effets isoles) : choisit local/cloud via policy.decide et
capture la PROVENANCE explicite dans les events (jamais de routage cache).

Backends factices (pas d'appel reseau). La decision reste VISIBLE dans le RouteResult
et dans les events captures.
"""
from multiservice.backends import Completion
from multiservice.events import EventType
from multiservice.routing import Router, RouteResult


class FakeBackend:
    """Backend deterministe pour les tests (ni reseau, ni modele)."""

    def __init__(self, model_id: str, count_source: str):
        self.model_id = model_id
        self.count_source = count_source

    def generate(self, composed_prompt: str) -> Completion:
        return self.chat([{"role": "user", "content": composed_prompt}])

    def chat(self, messages, on_token=None) -> Completion:
        last = messages[-1]["content"]
        return Completion(f"[{self.model_id}] {last}", self.model_id, 3, 5)


def _local():
    return FakeBackend("local-stub", "local_tokenizer")


def _cloud():
    return FakeBackend("sonar", "provider_usage")


def _provenance(events):
    """Recupere le bloc de provenance depuis l'event token_usage."""
    ev = next(e for e in events if e.type == EventType.TOKEN_USAGE)
    return ev.data


def test_cloud_path_provenance_cloud():
    r = Router(local=_local(), cloud=_cloud())
    res = r.route_turn("resume l'architecture", cloud_ok=True)
    assert isinstance(res, RouteResult)
    assert res.decision.route == "cloud"
    assert res.completion.model_id == "sonar"
    p = _provenance(res.events)
    assert p["routed_to"] == "cloud"
    assert p["routing_reason"] == "cloud_authorized_and_clean"
    assert p["cloud_ok"] is True and p["has_cloud"] is True
    assert p["sensitivity_reasons"] == []


def test_local_fallback_provenance_local():
    # cloud_ok=False -> fail-safe local, meme si un backend cloud existe.
    r = Router(local=_local(), cloud=_cloud())
    res = r.route_turn("question banale", cloud_ok=False)
    assert res.decision.route == "local"
    assert res.completion.model_id == "local-stub"
    p = _provenance(res.events)
    assert p["routed_to"] == "local"
    assert p["routing_reason"] == "cloud_not_authorized"
    assert p["has_cloud"] is True


def test_sensible_force_local_meme_avec_cloud():
    r = Router(local=_local(), cloud=_cloud())
    res = r.route_turn("ma cle sk-ABCDEF123456", cloud_ok=True)
    assert res.decision.route == "local"
    p = _provenance(res.events)
    assert p["routed_to"] == "local"
    assert p["routing_reason"] == "sensitive_input"
    assert any(s.startswith("secret:") for s in p["sensitivity_reasons"])


def test_pas_de_cloud_backend_reste_local():
    r = Router(local=_local(), cloud=None)
    res = r.route_turn("resume", cloud_ok=True)
    assert res.decision.route == "local"
    p = _provenance(res.events)
    assert p["has_cloud"] is False and p["routing_reason"] == "no_cloud_backend"


def test_capture_event_contient_provenance_complete():
    r = Router(local=_local(), cloud=_cloud())
    res = r.route_turn("resume l'architecture", cloud_ok=True)
    p = _provenance(res.events)
    for key in ("routed_to", "routing_reason", "sensitivity_reasons", "cloud_ok", "has_cloud"):
        assert key in p, key
    # count_source du backend choisi (cloud) doit etre porte par token_usage (D9).
    assert p["count_source"] == "provider_usage"
