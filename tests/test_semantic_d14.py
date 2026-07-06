"""D14 - recall hybride : cosine, store, build_index, rerank semantique, repli lexical."""
import io
import json
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import recall_semantic
from multiservice.semantic import EmbeddingStore, FakeEmbedder, OllamaEmbedder, build_index, cosine

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def test_ollama_embedder_tronque_les_inputs_a_6000(monkeypatch):
    """llama-server (ctx 4096) mouline puis rejette au-dela : on tronque a 6000 car AVANT l'envoi.
    Les textes courts passent inchanges."""
    from multiservice import semantic as sem
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        n = len(captured["body"]["input"])
        return _FakeResp(json.dumps({"embeddings": [[0.0]] * n}).encode("utf-8"))

    monkeypatch.setattr(sem, "urlopen", fake_urlopen)
    OllamaEmbedder().embed(["x" * 7000, "court"])
    sent = captured["body"]["input"]
    assert len(sent[0]) == 6000                       # tronque
    assert sent[1] == "court"                         # inchange


def test_build_index_batch_defaut_borne_a_4(tmp_path):
    """Defaut de batch conservateur (=4) : evite de saturer le serveur d'embedding."""
    class RecordingEmbedder:
        def __init__(self):
            self.sizes = []

        def embed(self, texts):
            self.sizes.append(len(texts))
            return [[float(len(t))] for t in texts]

    emb = RecordingEmbedder()
    store = EmbeddingStore(tmp_path / "e.jsonl")
    pairs = [(f"id{i}", f"texte {i}") for i in range(10)]
    build_index(pairs, emb, store)                    # sans batch -> defaut
    assert emb.sizes and max(emb.sizes) <= 4


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


def test_build_index_resilient_nan_et_echec(tmp_path):
    """Repli item-par-item si un batch echoue (500 NaN Ollama) ; vecteur NaN jamais stocke."""
    store = EmbeddingStore(tmp_path / "emb.jsonl")

    class BadEmbedder:
        def embed(self, texts):
            if len(texts) > 1:                       # simule le 500 d'Ollama en batch
                raise RuntimeError("HTTP 500 NaN")
            return [[float("nan"), 1.0]] if texts[0] == "bad" else [[0.1, 0.2]]

    pairs = [("a", "ok1"), ("bad", "bad"), ("c", "ok2")]
    added = build_index(pairs, BadEmbedder(), store, batch=8)
    assert added == 2                                # 'bad' (NaN) saute, 'a'/'c' stockes
    assert set(store.load()) == {"a", "c"}


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
