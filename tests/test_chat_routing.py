"""Tranche 1 (suite) - Router branche dans le flux de chat : le routage est REELLEMENT exerce.

On teste le coeur que chat.py utilise (`Router.generate`) + la capture de bout en bout
(`chat.record_turn` -> event final porte la provenance). Pas de boucle input() (non testable) :
on exerce la fonction de service du tour. Backends factices (ni reseau, ni modele).

Invariants : local par defaut ; cloud ssi cloud_ok ET has_cloud ET non sensible ;
cloud en echec (BackendError, ex cle absente) -> repli LOCAL, jamais de crash opaque ;
provenance toujours explicite dans l'event.
"""
from multiservice import chat
from multiservice.backends import BackendError, Completion, PerplexityBackend
from multiservice.events import EventType
from multiservice.journal import read_events
from multiservice.routing import Router


class FakeBackend:
    def __init__(self, model_id, count_source, fail_kind=None):
        self.model_id = model_id
        self.count_source = count_source
        self._fail = fail_kind

    def chat(self, messages, on_token=None):
        if self._fail:
            raise BackendError(self._fail, "echec simule")
        return Completion(f"[{self.model_id}]", self.model_id, 3, 5)

    def generate(self, composed_prompt):
        return self.chat([{"role": "user", "content": composed_prompt}])


def _local():
    return FakeBackend("local-stub", "local_tokenizer")


def _cloud():
    return FakeBackend("sonar", "provider_usage")


# --- Router.generate : la decision exercee comme dans chat.py ---

def test_sans_cloud_ok_reste_local():
    completion, cs, prov = Router(_local(), _cloud()).generate("salut", cloud_ok=False)
    assert completion.model_id == "local-stub" and cs == "local_tokenizer"
    assert prov["routed_to"] == "local" and prov["routing_reason"] == "cloud_not_authorized"


def test_cloud_ok_mais_pas_de_backend_cloud_reste_local():
    completion, cs, prov = Router(_local(), None).generate("salut", cloud_ok=True)
    assert completion.model_id == "local-stub"
    assert prov["routed_to"] == "local" and prov["has_cloud"] is False
    assert prov["routing_reason"] == "no_cloud_backend"


def test_non_sensible_cloud_present_va_au_cloud():
    completion, cs, prov = Router(_local(), _cloud()).generate("resume l'archi", cloud_ok=True)
    assert completion.model_id == "sonar" and cs == "provider_usage"
    assert prov["routed_to"] == "cloud" and prov["routing_reason"] == "cloud_authorized_and_clean"


def test_sensible_reste_local_meme_avec_cloud():
    completion, cs, prov = Router(_local(), _cloud()).generate("ma cle sk-ABCDEF123456", cloud_ok=True)
    assert completion.model_id == "local-stub"
    assert prov["routed_to"] == "local" and prov["routing_reason"] == "sensitive_input"
    assert any(s.startswith("secret:") for s in prov["sensitivity_reasons"])


def test_good_morning_va_au_cloud():
    # anti-faux-positif au niveau chat : "good morning" n'est pas sensible -> cloud.
    completion, cs, prov = Router(_local(), _cloud()).generate("good morning", cloud_ok=True)
    assert prov["routed_to"] == "cloud"


def test_perplexity_cle_absente_fallback_local():
    cloud = PerplexityBackend(api_key="")          # cle absente -> BackendError a l'appel
    completion, cs, prov = Router(_local(), cloud).generate("resume", cloud_ok=True)
    assert completion.model_id == "local-stub"     # le LOCAL a servi, pas de crash
    assert cs == "local_tokenizer"
    assert prov["routed_to"] == "local"
    assert prov["routing_reason"] == "cloud_error_fallback_local"
    assert prov["cloud_error"] == "missing_api_key"


# --- capture de bout en bout : l'event final porte la provenance ---

def test_event_final_contient_provenance(tmp_path):
    journal = tmp_path / "journal.jsonl"
    completion, cs, prov = Router(_local(), _cloud()).generate("resume l'archi", cloud_ok=True)
    n = chat.record_turn("resume l'archi", completion, cs, journal, "sess-1", routing=prov)
    assert n == 3
    evs = read_events(str(journal))
    tok = next(e for e in evs if e.type == EventType.TOKEN_USAGE)
    for key in ("routed_to", "routing_reason", "sensitivity_reasons", "cloud_ok", "has_cloud"):
        assert key in tok.data, key
    assert tok.data["routed_to"] == "cloud"
    assert tok.data["count_source"] == "provider_usage"
