"""Sprint 18 - Cache SEMANTIQUE (court-circuit du modele sur paraphrase quasi-identique).

Difference fondamentale avec le recall hybride (D14) :
  - le RECALL est SUGGESTIF (seuil bas tolere : il propose, l'agent tranche),
  - le CACHE est DECISIONNEL (il REMPLACE l'appel modele) -> seuil BEAUCOUP plus haut.
On ne sert que sur une paraphrase quasi-identique (cosinus >= THRESHOLD eleve), jamais sur un
simple voisinage de sujet. Regle d'or (heritee de cache.py) : DANS LE DOUTE, ON NE SERT PAS.

Garde C3 (jamais servir un perime) : une entree est invalidee par une `correction` posterieure
de la meme session -> on reutilise telle quelle `cache.is_valid` (source unique, pas de copie).

Cle = embedding du PROMPT UTILISATEUR (pas la liste de messages : l'historique change a chaque
tour, un hash exact n'y mordrait jamais). Embedding 100% LOCAL (Ollama) -> (c) preserve.

D15 : la DECISION (`semantic_select`) est PURE et testable ; seuls le store JSONL et l'embedder
touchent le monde. Append-only, on n'ecrase jamais (esprit C3).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .backends import Completion
from .cache import is_valid
from .events import AetherEvent
from .semantic import Embedder, cosine

DEFAULT_THRESHOLD = 0.95   # conservateur ; a CALIBRER sur le reel (scripts/semcache_probe.py)


def semantic_select(qvec: List[float], entries: Iterable[Dict[str, Any]],
                    journal_events: Iterable[AetherEvent] = (),
                    threshold: float = DEFAULT_THRESHOLD) -> Optional[Tuple[Dict[str, Any], float]]:
    """Meilleure entree servable pour qvec : cosinus >= threshold ET valide C3. PUR.
    Retourne (entree, similarite) ou None. Conservateur : aucun candidat sur -> None (on appelle
    le modele). Ne mute aucune entree."""
    journal_events = list(journal_events)
    best: Optional[Tuple[Dict[str, Any], float]] = None
    for e in entries:
        vec = e.get("vec")
        if not vec:
            continue
        sim = cosine(qvec, vec)
        if sim < threshold:
            continue
        if not is_valid(e, journal_events):          # garde C3 : cloture/correction -> on ne sert pas
            continue
        if best is None or sim > best[1]:
            best = (e, sim)
    return best


class SemanticCache:
    """Magasin append-only (JSONL) : prompt -> (embedding, reponse). La plus recente gagne."""

    def __init__(self, path: str | Path, embedder: Embedder) -> None:
        self.path = Path(path)
        self.embedder = embedder

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def get(self, prompt_text: str, session_id: Optional[str] = None,
            journal_events: Iterable[AetherEvent] = (),
            threshold: float = DEFAULT_THRESHOLD) -> Optional[Tuple[Completion, float]]:
        """Sert une reponse depuis le cache si une paraphrase quasi-identique valide existe.
        Retourne (Completion, similarite) ou None. Tout l'input est epargne sur un hit."""
        if not prompt_text.strip():
            return None
        qvec = self.embedder.embed([prompt_text])[0]
        hit = semantic_select(qvec, self._load(), journal_events, threshold)
        if hit is None:
            return None
        entry, sim = hit
        comp = Completion(
            text=entry["text"], model_id=entry["model_id"],
            input_tokens=entry["input_tokens"], output_tokens=entry["output_tokens"],
            cached_tokens=entry["input_tokens"],     # hit : tout l'input est epargne
        )
        return comp, sim

    def put(self, prompt_text: str, completion: Completion,
            session_id: Optional[str] = None, now: Optional[datetime] = None) -> None:
        if not prompt_text.strip():
            return
        vec = self.embedder.embed([prompt_text])[0]
        entry = {
            "prompt": prompt_text, "vec": vec, "session_id": session_id,
            "created_at": (now or datetime.now(timezone.utc)).isoformat(),
            "text": completion.text, "model_id": completion.model_id,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
