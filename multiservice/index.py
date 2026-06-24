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
               EventType.TOOL_RESULT,
               # raisonnement / projet : pour les retrouver PAR LE SENS (recall_semantic)
               EventType.DECISION, EventType.NOTE,
               EventType.HYPOTHESIS, EventType.OBSERVATION, EventType.VALIDATION}


def main() -> None:
    p = argparse.ArgumentParser(description="D14 - indexation embeddings locale (Ollama).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--store", default=config.EMBED_PATH)
    p.add_argument("--model", default=config.EMBED_MODEL)
    p.add_argument("--host", default=config.OLLAMA_HOST)
    # Petit batch : Ollama bge-m3 produit des NaN en embedding batch >= ~8 (bug serveur,
    # repond 500 "unsupported value: NaN"). 4 est sur ; baisser a 1 si un NaN persiste.
    p.add_argument("--batch", type=int, default=4)
    a = p.parse_args()
    events = read_events(a.journal)
    # Cap la longueur : bge-m3 (endpoint Ollama /api/embed) renvoie 500 sur des textes trop
    # longs. 6000 caracteres suffisent pour capter le sens au recall semantique.
    pairs = [(e.id, (e.data.get("text") or e.description or "")[:6000])
             for e in events if e.type in _TEXT_TYPES]
    store = EmbeddingStore(a.store)
    embedder = OllamaEmbedder(model=a.model, host=a.host)
    n = build_index(pairs, embedder, store, batch=a.batch)
    print(f"[index] {n} nouveaux embeddings ({a.model}) ajoutes -> {a.store}")
    print(f"        total textes candidats : {len(pairs)}")


if __name__ == "__main__":
    main()
