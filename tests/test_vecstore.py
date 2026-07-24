"""Store vectoriel BINAIRE — l'index derive n'a aucune raison de peser 5,5x son poids utile.

Mesure du 24/07/2026 sur le corpus reel : 2523 vecteurs MiniLM 384d occupaient **21 Mo** en JSONL,
soit 8504 octets par vecteur la ou float32 en demande **1536**. Le JSON ecrit `0.023847661` en
onze caracteres quand quatre octets suffisent. Et le relire coutait 0,79 s a chaque demarrage.

Deux proprietes visees :
  1. le VOLUME : format binaire compact, memmap, aucun parsing ;
  2. la RAM : on ne charge pas 300 Mo de float32 pour comparer 80 candidats. `vectors_for(ids)`
     lit CE qu'on demande, rien d'autre.

Le journal-verite, lui, reste du JSONL append-only : c'est la vérité auditable, pas un index.
"""
import struct

import pytest

from multiservice.vecstore import BinaryVectorStore


def _vecs(n=5, dim=8):
    return {"id-%02d" % i: [float(i) + j / 10.0 for j in range(dim)] for i in range(n)}


def test_round_trip_rend_les_memes_vecteurs(tmp_path):
    p = tmp_path / "index.vec"
    src = _vecs()
    BinaryVectorStore.write(p, src)
    relu = BinaryVectorStore(p).load()
    assert set(relu) == set(src)
    for k in src:
        assert all(abs(a - b) < 1e-6 for a, b in zip(relu[k], src[k]))


def test_volume_proche_du_theorique(tmp_path):
    """4 octets par dimension, plus un en-tete. Pas 8500 octets pour 384 dimensions."""
    p = tmp_path / "index.vec"
    BinaryVectorStore.write(p, _vecs(n=100, dim=384))
    theorique = 100 * 384 * 4
    assert p.stat().st_size < theorique * 1.10          # moins de 10 % d'en-tete et d'ids


def test_vectors_for_ne_rend_que_le_demande(tmp_path):
    p = tmp_path / "index.vec"
    BinaryVectorStore.write(p, _vecs(n=10))
    s = BinaryVectorStore(p)
    out = s.vectors_for(["id-03", "id-07", "inconnu"])
    assert set(out) == {"id-03", "id-07"}               # l'inconnu est ignore, pas une erreur
    assert abs(out["id-03"][0] - 3.0) < 1e-6


def test_ids_et_bits_sans_charger_les_float(tmp_path):
    """Le prefiltre Hamming doit tenir en RAM (48 o/vecteur en 384d) sans les float32."""
    p = tmp_path / "index.vec"
    BinaryVectorStore.write(p, _vecs(n=4, dim=384))
    s = BinaryVectorStore(p)
    assert len(s.ids()) == 4
    bits = s.bits()
    assert set(bits) == set(s.ids())
    assert all(len(b) == 384 // 8 for b in bits.values())


def test_fichier_etranger_refuse(tmp_path):
    """Un index est reconstructible : mieux vaut refuser franchement qu'interpreter du hasard."""
    p = tmp_path / "index.vec"
    p.write_bytes(b"ceci n'est pas un index" + struct.pack("<I", 3))
    with pytest.raises(ValueError):
        BinaryVectorStore(p).ids()


def test_index_absent_se_comporte_comme_un_index_vide(tmp_path):
    """Pas d'index -> repli lexical propre en amont, jamais une exception."""
    s = BinaryVectorStore(tmp_path / "pas-la.vec")
    assert s.load() == {} and s.ids() == [] and s.vectors_for(["x"]) == {}


# --- integration : recall_semantic ne doit plus charger tout l'index ---

class _StoreEspion:
    """Refuse `load()` : si le recall y touche encore, le test echoue franchement."""

    def __init__(self, vecs):
        self.vecs = vecs
        self.demandes = []

    def load(self):
        raise AssertionError("recall_semantic ne doit pas charger TOUT l'index")

    def vectors_for(self, ids):
        ids = list(ids)
        self.demandes.append(ids)
        return {i: self.vecs[i] for i in ids if i in self.vecs}


def _corpus(n=6):
    from datetime import datetime, timedelta, timezone
    from multiservice.events import AetherEvent, EventType
    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    evs = []
    for i in range(n):
        src = "project:cible" if i < 2 else "project:autre"
        evs.append(AetherEvent(type=EventType.DECISION, title="d", description="reacteur %d" % i,
                               source=src, observed_at=t0 + timedelta(minutes=i),
                               data={"text": "reacteur %d" % i, "session_id": "s", "turn_id": "t"}))
    return evs


def test_recall_semantic_ne_demande_que_les_candidats():
    """RAM proportionnelle aux CANDIDATS, pas au corpus : le filtre bi-temporel et le filtre
    source s'appliquent AVANT de reclamer des vecteurs."""
    from multiservice import memory
    from multiservice.semantic import FakeEmbedder
    evs = _corpus()
    emb = FakeEmbedder(dim=8)
    vecs = {e.id: emb.embed([e.description])[0] for e in evs}
    espion = _StoreEspion(vecs)

    hits = memory.recall_semantic(evs, "reacteur", emb, espion, k=5, source_prefix="project:cible")

    assert hits, "le recall doit fonctionner sans charger tout l'index"
    demandes = [i for lot in espion.demandes for i in lot]
    assert len(demandes) == 2, "seuls les 2 events de project:cible devaient etre reclames"
    assert all(h["source"] == "project:cible" for h in hits)


def test_recall_semantic_reste_compatible_avec_un_store_sans_vectors_for():
    """RETRO-COMPAT : un `EmbeddingStore` jsonl (ou tout store tiers) continue de marcher."""
    from multiservice import memory
    from multiservice.semantic import EmbeddingStore, FakeEmbedder
    import tempfile
    from pathlib import Path
    evs = _corpus(3)
    emb = FakeEmbedder(dim=8)
    with tempfile.TemporaryDirectory() as d:
        st = EmbeddingStore(Path(d) / "e.jsonl")
        st.add({e.id: emb.embed([e.description])[0] for e in evs})
        hits = memory.recall_semantic(evs, "reacteur", emb, st, k=5)
    assert hits


# --- migration depuis le jsonl + choix automatique du store ---

def test_migration_jsonl_vers_binaire_conserve_tout(tmp_path):
    from multiservice.semantic import EmbeddingStore
    from multiservice.vecstore import migrer_depuis_jsonl
    src = tmp_path / "e.jsonl"
    attendu = _vecs(n=20, dim=16)
    EmbeddingStore(src).add(attendu)

    dest = tmp_path / "e.vec"
    n = migrer_depuis_jsonl(src, dest)

    assert n == 20
    relu = BinaryVectorStore(dest).load()
    assert set(relu) == set(attendu)
    for k in attendu:
        assert all(abs(a - b) < 1e-6 for a, b in zip(relu[k], attendu[k]))
    assert dest.stat().st_size < src.stat().st_size      # c'est tout l'interet


def test_open_store_prefere_le_binaire_quand_il_existe(tmp_path):
    """Bascule sans changer la configuration : si l'index binaire est la, on le sert."""
    from multiservice.semantic import EmbeddingStore
    from multiservice.vecstore import open_store
    jsonl = tmp_path / "e.jsonl"
    EmbeddingStore(jsonl).add(_vecs(n=3, dim=8))
    assert isinstance(open_store(jsonl), EmbeddingStore)         # pas encore de .vec

    migrer = __import__("multiservice.vecstore", fromlist=["migrer_depuis_jsonl"])
    migrer.migrer_depuis_jsonl(jsonl, tmp_path / "e.vec")
    assert isinstance(open_store(jsonl), BinaryVectorStore)      # desormais oui


def test_open_store_sur_chemin_vec_direct(tmp_path):
    from multiservice.vecstore import open_store
    p = tmp_path / "index.vec"
    BinaryVectorStore.write(p, _vecs(n=2, dim=8))
    assert isinstance(open_store(p), BinaryVectorStore)
