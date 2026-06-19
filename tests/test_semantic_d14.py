"""D14 - recall hybride : cosine, store, build_index, rerank semantique, repli lexical."""
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import recall_semantic
from multiservice.semantic import EmbeddingStore, FakeEmbedder, build_index, cosine

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _ev(text, eid=None, at=T0):
    e = AetherEvent(type=EventType.COMPLETION, title="x", description=text,
                    source="llm:eve", observed_at=at, data={"text": text})
    if eid:
        object.__setattr__(e, "id", eid)
    return e


def test_cosine_borne():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
    assert cosine([], [1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0


def test_store_et_build_index_incremental(tmp_path):
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    emb = FakeEmbedder()
    pairs = [("a", "chien"), ("b", "voiture")]
    assert build_index(pairs, emb, store) == 2
    assert build_index(pairs, emb, store) == 0
    assert set(store.load()) == {"a", "b"}


def test_recall_semantic_reordonne_par_sens(tmp_path):
    evs = [_ev("le chien noir court", "a"), _ev("une voiture rouge roule", "b"),
           _ev("le chat et le chien dorment", "c")]
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    emb = FakeEmbedder()
    build_index([(e.id, e.data["text"]) for e in evs], emb, store)
    r = recall_semantic(evs, "chien", emb, store, k=3, explain=True)
    assert r and "fused" in r[0] and "semantic" in r[0] and "lexical" in r[0]
    assert r[0]["fused"] >= r[-1]["fused"]            # tri par score FUSIONNE
    assert "semantic_norm" in r[0] and "lexical_norm" in r[0]   # mode explain
    assert r[0]["id"] in ("a", "c")                   # chien passe devant la voiture


def test_recall_semantic_repli_lexical_si_pas_indexe(tmp_path):
    evs = [_ev("connecteur odbc hfsql", "a")]
    store = EmbeddingStore(tmp_path / "vide.jsonl")
    r = recall_semantic(evs, "odbc", FakeEmbedder(), store, k=3)
    assert len(r) == 1 and "score" in r[0]



def test_lexical_est_une_couverture_bornee():
    from multiservice.memory import _score
    assert _score("odbc connexion reset thread", "connexion reset") == 0.5   # 2/4
    assert _score("odbc connexion", "rien a voir") == 0.0
    assert 0.0 <= _score("a b c d", "a b c d e f g h i j") <= 1.0            # pas d'explosion par longueur
    assert _score("connexion odbc", "voici la connexion odbc directe") == 1.0  # phrase exacte


def test_min_fused_etouffe_le_bruit(tmp_path):
    evs = [_ev("le chien noir", "a"), _ev("voiture rouge", "b")]
    store = EmbeddingStore(tmp_path / "e.jsonl"); emb = FakeEmbedder()
    build_index([(e.id, e.data["text"]) for e in evs], emb, store)
    plein = recall_semantic(evs, "chien", emb, store, k=5, min_fused=0.0)
    filtre = recall_semantic(evs, "chien", emb, store, k=5, min_fused=0.5)
    assert len(filtre) <= len(plein)                    # le plancher coupe les faibles
    assert all(h["fused"] >= 0.5 for h in filtre)


def test_sem_weight_fait_pencher_la_fusion(tmp_path):
    # doc A : fort semantique / faible lexical ; doc B : faible semantique / fort lexical
    # On simule via FakeEmbedder + textes : query "chien" -> A parle de chien sans le mot,
    # B contient "chien" mais semantiquement loin. Difficile a garantir avec FakeEmbedder,
    # donc on teste l'effet du poids sur l'ORDRE via deux docs distincts.
    evs = [_ev("chien chien chien", "lex"),          # lexical fort (mot present)
           _ev("le chiot et le toutou", "sem")]       # pas le mot 'chien' -> lexical 0
    store = EmbeddingStore(tmp_path / "e.jsonl"); emb = FakeEmbedder()
    build_index([(e.id, e.data["text"]) for e in evs], emb, store)
    bas = recall_semantic(evs, "chien", emb, store, k=2, min_fused=0.0, sem_weight=0.1)
    haut = recall_semantic(evs, "chien", emb, store, k=2, min_fused=0.0, sem_weight=0.9)
    # a poids lexical fort (0.1 sem), le doc 'lex' (mot present) domine
    assert bas[0]["id"] == "lex"
    # le poids change bien la fusion (l'ordre ou les scores different)
    assert [h["id"] for h in bas] != [h["id"] for h in haut] or bas[0]["fused"] != haut[0]["fused"]
