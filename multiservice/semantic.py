"""Sprint D14 - Recall hybride : couche SEMANTIQUE suggestive, embedding LOCAL.

Principe (DECISIONS D14) : la bi-temporalite (C3) reste la porte decisionnelle ; l'embedding
ne fait que RE-ORDONNER les candidats valides (suggestif, jamais decisionnaire), toujours
double d'une provenance. Embedding 100% LOCAL (Ollama /api/embed) -> aucune API hebergee,
(c) preserve. Si pas d'embedder / pas d'index -> repli lexical (rien ne casse).

  Embedder      : protocole embed(texts)->vecteurs. FakeEmbedder pour les tests.
  OllamaEmbedder: appelle l'endpoint local (import/IO au bord). Lazy.
  EmbeddingStore: cache jsonl id->vecteur (append-only), construit par build_index().
  cosine / rerank : purs, testables.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence
from urllib.request import Request, urlopen


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Similarite cosinus. PUR. 0 si l'un des vecteurs est nul ou tailles differentes."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class FakeEmbedder:
    """Embedder deterministe pour tests (sac de caracteres sur dim dimensions). PUR."""

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for ch in t.lower():
                v[ord(ch) % self.dim] += 1.0
            out.append(v)
        return out


class OllamaEmbedder:
    """Embedding LOCAL via Ollama (http://localhost:11434/api/embed). Coquille I/O."""

    def __init__(self, model: str = "bge-m3", host: str = "http://localhost:11434",
                 timeout: int = 120) -> None:
        self.model = model
        self._url = host.rstrip("/") + "/api/embed"
        self._timeout = timeout

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": list(texts)}
        req = Request(self._url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=self._timeout) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        return r.get("embeddings") or ([r["embedding"]] if "embedding" in r else [])


class EmbeddingStore:
    """Cache append-only id->vecteur (jsonl). On n'efface jamais (esprit C3)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._cache: Optional[Dict[str, List[float]]] = None

    def load(self) -> Dict[str, List[float]]:
        if self._cache is None:
            d: Dict[str, List[float]] = {}
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        o = json.loads(line)
                        d[o["id"]] = o["vec"]          # derniere occurrence gagne
            self._cache = d
        return self._cache

    def add(self, entries: Dict[str, List[float]]) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for eid, vec in entries.items():
                f.write(json.dumps({"id": eid, "vec": vec}) + "\n")
        if self._cache is not None:
            self._cache.update(entries)
        return len(entries)


def build_index(id_text_pairs: List[tuple], embedder: Embedder, store: EmbeddingStore,
                batch: int = 32) -> int:
    """Embed les (id, texte) PAS ENCORE dans le store. Retourne le nb ajoute. Incremental."""
    have = store.load()
    todo = [(eid, txt) for eid, txt in id_text_pairs if eid not in have and txt.strip()]
    added = 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        vecs = embedder.embed([t for _, t in chunk])
        entries = {eid: vec for (eid, _), vec in zip(chunk, vecs)}
        added += store.add(entries)
    return added
