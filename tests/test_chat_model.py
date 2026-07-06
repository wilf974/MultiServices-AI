"""Le modele est un CHOIX, jamais fige : with_model garde la config et ne mute rien.

Contrat : OllamaBackend.with_model(nom) -> NOUVEAU backend, meme host/timeout/think/options ;
l'original est intact (les tours deja captures gardent leur model_id, C2). Demande <user>
du 01/07/2026 : « je dois pouvoir choisir le modele, cela ne doit pas etre fige ».

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from multiservice.backends import OllamaBackend, StubBackend


def test_with_model_change_le_modele_et_garde_la_config():
    b = OllamaBackend(model="eve-qwen3-8b", host="http://h:1234", timeout=42,
                      think=True, options={"num_ctx": 8192})
    nb = b.with_model("qwen3.6:latest")
    assert nb.model_id == "qwen3.6:latest"
    assert nb._url == b._url                    # meme hote Ollama
    assert nb._timeout == 42 and nb._think is True
    assert nb._options == {"num_ctx": 8192}
    assert nb._options is not b._options        # copie, pas de partage mutable


def test_with_model_ne_mute_pas_l_original():
    b = OllamaBackend(model="eve-qwen3-8b")
    nb = b.with_model("autre-modele")
    assert b.model_id == "eve-qwen3-8b"         # C2 : les tours passes gardent leur modele
    assert nb is not b


def test_le_stub_n_offre_pas_le_changement_en_vol():
    # /model ne s'applique qu'au backend Ollama ; le stub (tests) n'a pas with_model.
    assert not hasattr(StubBackend(), "with_model")
