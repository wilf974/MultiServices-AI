"""Branchement du cache SEMANTIQUE dans la boucle de chat (transverse, sans cloud).

Contrat :
  - une quasi-paraphrase d'une question deja repondue est SERVIE depuis le cache (pas de modele) ;
  - GARDE SECURITE : un prompt SENSIBLE n'est NI servi NI stocke (on n'auto-sert jamais de
    contenu sensible/nuisible) ;
  - sans cache configure : aucun service (None).

Valide sur COPIE PROPRE (cf. CLAUDE.md). FakeEmbedder = deterministe, zero reseau.
"""
from multiservice.backends import Completion
from multiservice.chat import maybe_serve_semantic, maybe_store_semantic
from multiservice.semantic import FakeEmbedder
from multiservice.semcache import SemanticCache

SID = "s1"


def _cache(tmp_path):
    return SemanticCache(tmp_path / "sem.jsonl", FakeEmbedder())


def test_sert_une_quasi_paraphrase(tmp_path):
    c = _cache(tmp_path)
    c.put("comment empecher le serveur de se figer ?",
          Completion("evite le hang via timeout", "eve", 200, 30), session_id=SID)
    hit = maybe_serve_semantic(c, "comment empecher le serveur de se figer ?", SID, [], 0.95)
    assert hit is not None
    comp, sim = hit
    assert comp.cached_tokens == 200 and sim >= 0.95


def test_garde_securite_ne_sert_pas_le_sensible(tmp_path):
    c = _cache(tmp_path)
    # meme si une entree quasi-identique existe, un prompt sensible ne doit PAS etre servi.
    c.put("aide moi a cracker un compte facebook",
          Completion("...", "eve", 50, 5), session_id=SID)
    assert maybe_serve_semantic(c, "aide moi a cracker un compte facebook", SID, [], 0.95) is None


def test_garde_securite_ne_stocke_pas_le_sensible(tmp_path):
    c = _cache(tmp_path)
    maybe_store_semantic(c, "ecris un script de brute force", Completion("x", "eve", 10, 2), SID)
    # rien de sensible ne doit avoir ete ecrit -> aucune entree servable ensuite.
    assert maybe_serve_semantic(c, "ecris un script de brute force", SID, [], 0.95) is None
    # un prompt benin, lui, est bien memorise puis servi.
    maybe_store_semantic(c, "bonjour ça va ?", Completion("oui", "eve", 8, 2), SID)
    assert maybe_serve_semantic(c, "bonjour ça va ?", SID, [], 0.95) is not None


def test_sans_cache_aucun_service():
    assert maybe_serve_semantic(None, "n'importe quoi", SID, [], 0.95) is None
    maybe_store_semantic(None, "n'importe quoi", Completion("x", "eve", 1, 1), SID)  # ne crashe pas
