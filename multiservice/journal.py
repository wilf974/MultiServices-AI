"""Journal-verite append-only (JSONL). Coquille a effet de bord, ISOLEE au bord.

On n'ECRASE jamais, on n'efface jamais : on append. (C3 : cloture, pas suppression.)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .events import AetherEvent


def append_events(path: str | Path, events: List[AetherEvent]) -> int:
    """Ajoute des evenements en fin de journal. Retourne le nombre ecrit."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
    return len(events)


def read_events(path: str | Path) -> List[AetherEvent]:
    """Relit le journal (pour tests / replay). Vide si absent."""
    p = Path(path)
    if not p.exists():
        return []
    out: List[AetherEvent] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(AetherEvent.model_validate_json(line))
    return out
