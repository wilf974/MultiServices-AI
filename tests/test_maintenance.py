"""Maintenance memoire (donnee DERIVEE) : reindexation incrementale + rapport de couverture.
Housekeeping mecanique, pas d'action autoritaire (le journal n'est jamais mute). Embedder injecte
(FakeEmbedder) -> pas d'Ollama en test.
"""
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events
from multiservice.maintenance import coverage_report, reindex
from multiservice.semantic import FakeEmbedder


def _seed(path):
    ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
    evs = [
        AetherEvent(type=EventType.NOTE, title="n", description="cache nimbus 42",
                    source="s", observed_at=ts, data={"text": "le cache nimbus cible 42 ms"}),
        AetherEvent(type=EventType.DECISION, title="d", description="decision cache",
                    source="s", observed_at=ts, data={"text": "decision sur le cache"}),
    ]
    append_events(str(path), evs)
    return str(path)


def test_reindex_incremental_et_idempotent(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    sp = str(tmp_path / "emb.jsonl")
    r = reindex(journal_path=jp, store_path=sp, embedder=FakeEmbedder())
    assert r["candidates"] >= 2 and r["added"] == r["candidates"]
    assert r["coverage"]["missing"] == 0 and r["coverage"]["fresh"] is True
    r2 = reindex(journal_path=jp, store_path=sp, embedder=FakeEmbedder())
    assert r2["added"] == 0                    # incremental : rien de neuf a re-embed


def test_check_ne_reconstruit_pas(tmp_path):
    jp = _seed(tmp_path / "j.jsonl")
    sp = str(tmp_path / "emb.jsonl")
    c = coverage_report(journal_path=jp, store_path=sp)
    assert c["eligible"] >= 2 and c["indexed"] == 0 and c["fresh"] is False
