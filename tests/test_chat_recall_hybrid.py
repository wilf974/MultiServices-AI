"""Secondaire — injection HYBRIDE : build_recall_context via recall_semantic quand dispo.

Contrat : avec embedder+store, l'injection passe par le canal semantique (hits portant `fused`) ;
sans, repli lexical. Le bloc reste filtre (sensible exclu), borne, et la session courante exclue.

Valide sur COPIE PROPRE (cf. CLAUDE.md). FakeEmbedder = deterministe.
"""
from datetime import datetime, timezone

from multiservice.chat import build_recall_context
from multiservice.events import AetherEvent, EventType
from multiservice.semantic import EmbeddingStore, FakeEmbedder, build_index

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)


def _ev(text, sid="vieille"):
    return AetherEvent(type=EventType.COMPLETION, title="x", description=text, source="llm:eve",
                       observed_at=T0, data={"text": text, "turn_id": "t1", "session_id": sid})


def _indexed_store(tmp_path, events):
    store = EmbeddingStore(tmp_path / "emb.jsonl")
    build_index([(e.id, e.data["text"]) for e in events], FakeEmbedder(), store)
    return store


def test_injection_hybride_utilise_le_semantique(tmp_path):
    evs = [_ev("le pool de connexions odbc tient huit connexions")]
    store = _indexed_store(tmp_path, evs)
    ctx = build_recall_context(evs, "pool de connexions odbc", session_id="courante",
                               min_score=0.1, embedder=FakeEmbedder(), store=store)
    assert "pool de connexions" in ctx.lower()
    assert ctx.startswith("[Memoire")


def test_repli_lexical_sans_embedder():
    evs = [_ev("le pool de connexions odbc tient huit connexions")]
    ctx = build_recall_context(evs, "pool connexions odbc", session_id="courante", min_score=0.1)
    assert "pool de connexions" in ctx.lower()


def test_hybride_exclut_session_courante(tmp_path):
    evs = [_ev("pool de connexions odbc", sid="courante")]
    store = _indexed_store(tmp_path, evs)
    ctx = build_recall_context(evs, "pool connexions odbc", session_id="courante",
                               min_score=0.1, embedder=FakeEmbedder(), store=store)
    assert ctx == ""        # le seul souvenir est dans la session courante -> rien a injecter
