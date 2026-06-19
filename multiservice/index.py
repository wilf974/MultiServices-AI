"""D14 - Indexation des embeddings (batch, local). A lancer apres avoir chatte.

Embed les evenements textuels du journal (prompt/completion/...) via Ollama LOCAL et
stocke les vecteurs dans le cache. Incremental : ne re-embed que le nouveau.
Usage : python -m multiservice.index            (modele bge-m3 par defaut)
        python -m multiservice.index --model nomic-embed-text
"""
from __future__ import annotations

import argparse

from . import config
from .events import EventType
from .journal import read_events
from .semantic import EmbeddingStore, OllamaEmbedder, build_index

_TEXT_TYPES = {EventType.PROMPT, EventType.COMPLETION, EventType.CORRECTION,
               EventType.TOOL_RESULT}


def main() -> None:
    p = argparse.ArgumentParser(description="D14 - indexation embeddings locale (Ollama).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--store", default=config.EMBED_PATH)
    p.add_argument("--model", default=config.EMBED_MODEL)
    p.add_argument("--host", default=config.OLLAMA_HOST)
    a = p.parse_args()
    events = read_events(a.journal)
    pairs = [(e.id, (e.data.get("text") or e.description or ""))
             for e in events if e.type in _TEXT_TYPES]
    store = EmbeddingStore(a.store)
    embedder = OllamaEmbedder(model=a.model, host=a.host)
    n = build_index(pairs, embedder, store)
    print(f"[index] {n} nouveaux embeddings ({a.model}) ajoutes -> {a.store}")
    print(f"        total textes candidats : {len(pairs)}")


if __name__ == "__main__":
    main()
