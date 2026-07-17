"""Canal VECTORIEL BINAIRE de la projection (decision 0407c17a, local-only).

Quantization binaire (1 bit/dim, signe > 0) + re-score float32 : la projection stocke les BITS
(128 o/vecteur en bge-m3), l'EmbeddingStore jsonl GARDE les float32 (verite reconstructible).
Le Hamming top-M n'est qu'un PREFILTRE (union candidats FTS + top-M + corrections C3) ; les
fonctions pures de `memory` restent le moteur ET l'oracle (re-score cosinus float32).
Invariants : oracle EGAL quand M couvre le corpus, evict (crypto-shredding) PROPAGE aux bits,
une seule passe d'embedding par requete, le journal n'est jamais ecrit."""
import sqlite3

from multiservice import memory, project, projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events
from multiservice.semantic import EmbeddingStore, FakeEmbedder, build_index, hamming, pack_bits


def _ev(title, source="project:demo"):
    return AetherEvent(type=EventType.NOTE, title=title, source=source)


def _setup(tmp_path, titles):
    """Journal + projection rattrapee + store d'embeddings (FakeEmbedder) synchronise."""
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev(t) for t in titles])
    evs = read_events(journal)
    p = projection.Projection(tmp_path / "proj.db")
    p.update(journal)
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    emb = FakeEmbedder()
    build_index([(e.id, e.title) for e in evs], emb, store)
    p.sync_vectors(store)
    return journal, p, store, emb, evs


# --- primitives pures ---

def test_pack_bits_signe_et_padding():
    bits = pack_bits([1.0, -1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0])   # 9 dims -> 2 octets
    assert bits == bytes([0b10100000, 0b10000000])


def test_hamming_compte_les_bits_differents():
    a = pack_bits([1, 1, -1, -1])
    b = pack_bits([1, -1, 1, -1])
    assert hamming(a, a) == 0
    assert hamming(a, b) == 2 and hamming(b, a) == 2


# --- sync du canal binaire (projection <- store float32) ---

def test_sync_vectors_incremental_et_evict_propage(tmp_path):
    p = projection.Projection(tmp_path / "proj.db")
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    store.add({"a": [1.0, -1.0], "b": [-1.0, 1.0]})
    assert p.sync_vectors(store) == {"added": 2, "removed": 0, "total": 2}
    store.add({"c": [1.0, 1.0]})
    assert p.sync_vectors(store) == {"added": 1, "removed": 0, "total": 3}
    store.evict("a")                                       # crypto-shredding RGPD (fuite 2bis)
    assert p.sync_vectors(store) == {"added": 0, "removed": 1, "total": 2}
    ids = {r[0] for r in p.conn.execute("SELECT id FROM vecs")}
    assert ids == {"b", "c"}                               # les bits derives du clair efface ont disparu


def test_topk_hamming_ordonne_et_borne(tmp_path):
    p = projection.Projection(tmp_path / "proj.db")
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    store.add({"loin": [-1.0] * 8, "proche": [1.0] * 8, "mi": [1.0] * 4 + [-1.0] * 4})
    p.sync_vectors(store)
    q = pack_bits([1.0] * 8)
    assert p.topk_hamming(q, 3) == ["proche", "mi", "loin"]
    assert p.topk_hamming(q, 2) == ["proche", "mi"]        # borne a M


# --- recall semantique servi par la projection ---

def test_recall_semantic_sql_oracle_egal_pur(tmp_path):
    journal, p, store, emb, evs = _setup(
        tmp_path, ["moteur NEMA-17 cale", "servo MG996R brule", "capteur DHT22 humidite",
                   "le moteur chauffe", "note sans rapport aucun"])
    for q in ("moteur", "servo brule", "humidite capteur", "rien"):
        got = projection.recall_semantic_sql(p, q, emb, store, m=100, k=5,
                                             min_fused=0.0, sem_weight=0.7)
        want = memory.recall_semantic(read_events(journal), q, emb, store, k=5,
                                      min_fused=0.0, sem_weight=0.7)
        assert got == want                                 # ORACLE : M couvre le corpus -> egalite


def test_prefiltre_binaire_trouve_le_semantique_sans_lexical(tmp_path):
    # FakeEmbedder = sac de caracteres : 'niche' et 'chien' ont le MEME vecteur (anagramme),
    # mais AUCUN recouvrement lexical de tokens -> le FTS seul ne le proposerait pas.
    journal, p, store, emb, evs = _setup(
        tmp_path, ["niche", "zzz bruit 1", "zzz bruit 2", "zzz bruit 3"])
    got = projection.recall_semantic_sql(p, "chien", emb, store, m=1, k=3,
                                         min_fused=0.0, sem_weight=0.7)
    assert [h["id"] for h in got][:1] == [evs[0].id]       # retrouve par le SENS via le top-M binaire


def test_une_seule_passe_d_embedding_par_requete(tmp_path):
    journal, p, store, emb, evs = _setup(tmp_path, ["alpha beta", "gamma delta"])

    class Counting:
        def __init__(self, inner): self.inner, self.calls = inner, 0
        def embed(self, texts):
            self.calls += 1
            return self.inner.embed(texts)

    c = Counting(emb)
    projection.recall_semantic_sql(p, "alpha", c, store, m=10, k=3)
    assert c.calls == 1                                    # le qvec du prefiltre est REUTILISE au re-score


def test_schema_v3_reset_depuis_v2(tmp_path):
    db = tmp_path / "proj.db"
    conn = sqlite3.connect(str(db))                        # simule une base P1 (schema 2)
    conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO meta VALUES ('schema','2'),('line_count','7')")
    conn.execute("CREATE TABLE events (line_no INTEGER PRIMARY KEY)")
    conn.commit(); conn.close()
    p = projection.Projection(db)                          # derive perime -> etat vierge
    assert p._get("schema") == projection._SCHEMA and p._get("line_count", "0") == "0"
    assert p.conn.execute("SELECT count(*) FROM vecs").fetchone()[0] == 0


def test_canal_vectoriel_n_ecrit_jamais_le_journal(tmp_path):
    journal, p, store, emb, evs = _setup(tmp_path, ["un", "deux"])
    before = journal.read_bytes()
    p.sync_vectors(store)
    projection.recall_semantic_sql(p, "un", emb, store, m=10, k=3)
    assert journal.read_bytes() == before


def test_main_vectors_synchronise(tmp_path, capsys):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("un"), _ev("deux")])
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    build_index([(e.id, e.title) for e in read_events(journal)], FakeEmbedder(), store)
    project.main(["--journal", str(journal), "--db", str(tmp_path / "proj.db"),
                  "--vectors", "--embed", str(tmp_path / "emb.jsonl")])
    out = capsys.readouterr().out
    assert "added=2" in out and "total=2" in out
