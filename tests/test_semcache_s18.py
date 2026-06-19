"""Sprint 18 - test de regression : cache SEMANTIQUE (decisionnel, C3-correct).

Contrat (feuille de route S18) :
  - sert UNIQUEMENT sur paraphrase quasi-identique (cosinus >= seuil eleve),
  - JAMAIS sur un simple voisinage de sujet (sous le seuil -> on appelle le modele),
  - garde C3 : une correction posterieure de la session invalide le hit (perime -> non servi),
  - la decision est PURE (ne mute aucune entree),
  - regle d'or : dans le doute, on NE sert PAS.

Valide sur COPIE PROPRE (cf. CLAUDE.md). FakeEmbedder = embedding deterministe, zero reseau.
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.backends import Completion
from multiservice.events import AetherEvent, EventType
from multiservice.semantic import FakeEmbedder
from multiservice.semcache import SemanticCache, semantic_select

T0 = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)
SID = "sess-1"


def _entry(vec, created=T0, sid=SID):
    return {"vec": vec, "session_id": sid, "created_at": created.isoformat(),
            "text": "reponse mise en cache", "model_id": "eve",
            "input_tokens": 100, "output_tokens": 20}


def test_select_sert_la_paraphrase_quasi_identique():
    e = _entry([1.0, 0.0, 0.0])
    hit = semantic_select([1.0, 0.0, 0.0], [e], threshold=0.95)
    assert hit is not None and hit[1] >= 0.95


def test_select_ne_sert_pas_le_simple_voisinage():
    # vecteurs « meme sujet » mais distincts : cosinus ~0.7 < seuil 0.95 -> pas de hit.
    e = _entry([1.0, 1.0, 0.0])
    hit = semantic_select([1.0, 0.0, 0.0], [e], threshold=0.95)
    assert hit is None, "voisinage de sujet ne doit PAS court-circuiter le modele"


def test_select_choisit_le_plus_proche():
    e1 = _entry([1.0, 0.05, 0.0]); e1["text"] = "proche"
    e2 = _entry([1.0, 0.0, 0.0]); e2["text"] = "identique"
    hit = semantic_select([1.0, 0.0, 0.0], [e1, e2], threshold=0.9)
    assert hit is not None and hit[0]["text"] == "identique"


def test_select_garde_c3_invalide_le_hit():
    e = _entry([1.0, 0.0, 0.0])
    corr = AetherEvent(type=EventType.CORRECTION, title="correction", source="user:wilfred",
                       observed_at=T0 + timedelta(minutes=5),
                       data={"session_id": SID})
    hit = semantic_select([1.0, 0.0, 0.0], [e], journal_events=[corr], threshold=0.95)
    assert hit is None, "C3 : une correction posterieure perime l'entree -> on ne sert pas"


def test_select_est_pur():
    e = _entry([1.0, 0.0, 0.0])
    snap = copy.deepcopy(e)
    semantic_select([1.0, 0.0, 0.0], [e], threshold=0.95)
    assert e == snap, "la decision ne doit muter aucune entree"


def test_store_roundtrip_hit_et_miss(tmp_path):
    cache = SemanticCache(tmp_path / "sem.jsonl", FakeEmbedder())
    cache.put("comment empecher le serveur de se figer ?",
              Completion("evite le hang via timeout", "eve", 120, 30), session_id=SID, now=T0)
    # meme prompt -> hit (input epargne)
    got = cache.get("comment empecher le serveur de se figer ?", threshold=0.95)
    assert got is not None
    comp, sim = got
    assert comp.cached_tokens == 120 and sim >= 0.95
    # prompt franchement different (profil de caracteres distinct) -> pas de hit a seuil eleve
    miss = cache.get("zzzz wwww kkkk qqqq", threshold=0.95)
    assert miss is None
