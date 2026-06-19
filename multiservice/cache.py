"""Sprint 16 - Cache de resultat (exact, C3-correct). Premiere brique qui AGIT.

Principe : si la MEME requete (liste de messages identique) a deja ete repondue, on sert
la reponse depuis le cache et on N'APPELLE PAS le modele (economise entree ET sortie).

Garde C3 (regle d'or, jamais servir un resultat perime) : une entree est invalidee si une
`correction` survient APRES sa creation dans la MEME session (cloture C3). Choix de portee
v1 : par session (une correction en session X n'invalide que le cache de X). A elargir
plus tard si besoin. Conservateur par construction : en cas de doute, on NE sert pas.

Pur cote DECISION (request_key, is_valid) ; seul le magasin JSONL touche le disque
(append-only, jamais d'ecrasement - esprit C3). Test structurel : ce module n'appelle
aucun modele, aucun reseau.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .backends import Completion, Message
from .events import AetherEvent, EventType


def request_key(messages: List[Message]) -> str:
    """Cle stable d'une requete : hash du (role, content) ordonne. PUR."""
    norm = [{"role": m["role"], "content": m["content"]} for m in messages]
    blob = json.dumps(norm, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _has_closing_correction(session_id: Optional[str], created_at: datetime,
                            journal_events: Iterable[AetherEvent]) -> bool:
    """Vrai si une `correction` de la meme session est survenue apres created_at (C3)."""
    for e in journal_events:
        if e.type != EventType.CORRECTION:
            continue
        if e.data.get("session_id") != session_id:
            continue
        vf = e.valid_from
        if vf is not None and vf > created_at:
            return True
    return False


def is_valid(entry: Dict[str, Any], journal_events: Iterable[AetherEvent] = ()) -> bool:
    """Une entree de cache est-elle encore servable ? PUR (decision seule)."""
    created = entry["created_at"]
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    return not _has_closing_correction(entry.get("session_id"), created, journal_events)


class ResultCache:
    """Magasin append-only (JSONL) cle -> reponse. La derniere entree d'une cle gagne."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def get(self, messages: List[Message], session_id: Optional[str] = None,
            journal_events: Iterable[AetherEvent] = ()) -> Optional[Completion]:
        key = request_key(messages)
        match: Optional[Dict[str, Any]] = None
        for e in self._load():
            if e["key"] == key:
                match = e                     # append-only : on garde la plus recente
        if match is None or not is_valid(match, journal_events):
            return None
        return Completion(
            text=match["text"], model_id=match["model_id"],
            input_tokens=match["input_tokens"], output_tokens=match["output_tokens"],
            cached_tokens=match["input_tokens"],   # tout l'input est epargne sur un hit
        )

    def put(self, messages: List[Message], completion: Completion,
            session_id: Optional[str] = None, now: Optional[datetime] = None) -> None:
        entry = {
            "key": request_key(messages),
            "session_id": session_id,
            "created_at": (now or datetime.now(timezone.utc)).isoformat(),
            "text": completion.text, "model_id": completion.model_id,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
