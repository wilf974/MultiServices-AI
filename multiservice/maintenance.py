"""Maintenance de la memoire (donnee DERIVEE) : reindexation INCREMENTALE des embeddings.

Housekeeping MECANIQUE, pas d'action autoritaire : le journal append-only n'est JAMAIS mute, aucune
promotion / suppression / jugement. On entretient seulement la donnee derivee (index semantique),
comme la garde C3 perime deja le cache toute seule. Concu pour tourner sur un TIMER (cron / Task
Scheduler) : idempotent, incremental (ne re-embed que le neuf), sortie compacte pour les logs.

Usage : python -m multiservice.maintenance            # reindex incremental + rapport
        python -m multiservice.maintenance --check    # couverture seule (aucun rebuild)
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import config, memory
from .index import _TEXT_TYPES
from .journal import read_events
from .semantic import EmbeddingStore, OllamaEmbedder, build_index


def _pairs(events) -> List[Tuple[str, str]]:
    return [(e.id, (e.data.get("text") or e.description or "")[:6000])
            for e in events if e.type in _TEXT_TYPES]


def coverage_report(journal_path: Optional[str] = None, store_path: Optional[str] = None) -> dict:
    """Couverture de l'index (LECTURE SEULE) : eligible / indexed / missing / covered_pct / fresh."""
    events = read_events(journal_path or config.JOURNAL_PATH)
    store = EmbeddingStore(store_path or config.EMBED_PATH)
    return memory.index_coverage(events, store.load())


def reindex(journal_path: Optional[str] = None, store_path: Optional[str] = None,
            model: Optional[str] = None, host: Optional[str] = None, batch: int = 4,
            embedder=None) -> dict:
    """Reindexation INCREMENTALE (n'embarque que les nouveaux events). Retourne
    {added, candidates, coverage}. `embedder` injectable (tests, sans Ollama)."""
    events = read_events(journal_path or config.JOURNAL_PATH)
    pairs = _pairs(events)
    store = EmbeddingStore(store_path or config.EMBED_PATH)
    if embedder is None:
        embedder = OllamaEmbedder(model=model or config.EMBED_MODEL, host=host or config.OLLAMA_HOST)
    added = build_index(pairs, embedder, store, batch=batch)
    return {"added": added, "candidates": len(pairs),
            "coverage": memory.index_coverage(events, store.load())}


def _line(tag: str, cov: dict, extra: str = "") -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (f"[maintenance {ts}] {tag}: {extra}couverture {cov['covered_pct']}% "
            f"({cov['indexed']}/{cov['eligible']}), fresh={cov['fresh']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Maintenance memoire : reindex incremental des embeddings.")
    p.add_argument("--check", action="store_true", help="rapport de couverture seul (pas de rebuild)")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--store", default=config.EMBED_PATH)
    p.add_argument("--model", default=config.EMBED_MODEL)
    p.add_argument("--host", default=config.OLLAMA_HOST)
    p.add_argument("--batch", type=int, default=4)
    a = p.parse_args()
    if a.check:
        print(_line("check", coverage_report(a.journal, a.store)))
        return
    r = reindex(a.journal, a.store, a.model, a.host, a.batch)
    print(_line("reindex", r["coverage"], extra=f"+{r['added']} embeddings, "))


if __name__ == "__main__":
    main()
