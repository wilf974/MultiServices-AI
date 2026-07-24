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
from .semantic import EmbeddingStore, OllamaEmbedder, OnnxEmbedder, build_index

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
    # ONNX local (MiniLM 384d) : le corpus s'indexe ICI, seuls les vecteurs voyagent vers le
    # central (qui n'embeddera plus que des REQUETES, sans Ollama ni reindexation).
    p.add_argument("--onnx", action="store_true", help="embedder ONNX local au lieu d'Ollama")
    p.add_argument("--onnx-dir", default=config.ONNX_DIR)
    p.add_argument("--threads", type=int, default=4, help="threads ONNX (indexation)")
    a = p.parse_args()
    events = read_events(a.journal)
    # Cap la longueur : bge-m3 (endpoint Ollama /api/embed) renvoie 500 sur des textes trop
    # longs. 6000 caracteres suffisent pour capter le sens au recall semantique.
    pairs = [(e.id, (e.data.get("text") or e.description or "")[:6000])
             for e in events if e.type in _TEXT_TYPES]
    store = EmbeddingStore(a.store)
    if a.onnx:
        embedder = OnnxEmbedder(a.onnx_dir, threads=a.threads)
        nom = "onnx:all-MiniLM-L6-v2"
    else:
        embedder = OllamaEmbedder(model=a.model, host=a.host)
        nom = a.model
    n = build_index(pairs, embedder, store, batch=a.batch)
    print(f"[index] {n} nouveaux embeddings ({nom}) ajoutes -> {a.store}")
    print(f"        total textes candidats : {len(pairs)}")


if __name__ == "__main__":
    main()
