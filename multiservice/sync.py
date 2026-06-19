"""Synchro de journal — le COEUR : fusionner un journal source DANS la cible, append-only.

Ajoute uniquement les events dont l'`id` manque dans la cible. **Idempotent** (re-fusionner
n'ajoute rien), **jamais** de réécriture ni de suppression (esprit C3, journal append-only).
C'est la pièce réutilisable de TOUTE synchro multi-machines : le transport (clé USB, dossier
partagé, plus tard un endpoint réseau type collecteur AetherCore) n'est qu'une enveloppe qui amène
le fichier source à portée ; la fusion, elle, est la même.

Modèle recommandé : chaque machine écrit SON propre journal (pas d'écriture concurrente sur un
fichier partagé) ; on FUSIONNE périodiquement les journaux distants dans le journal hôte.

Lancer : python -m multiservice.sync --from <journal-source> [--to <journal-hote>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from . import config


def _ids_and_lines(path: Path):
    """(set des ids presents, liste des lignes brutes valides) d'un journal jsonl. Tolerant."""
    ids = set()
    lines = []
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                oid = json.loads(raw).get("id")
            except json.JSONDecodeError:
                continue                       # ligne corrompue : ignoree, jamais reecrite
            ids.add(oid)
            lines.append((oid, raw))
    return ids, lines


def merge_journal(target_path, source_path) -> Dict[str, Any]:
    """Fusionne `source` DANS `target` : append-only, dedup par id, idempotent. PUR (IO au bord)."""
    target = Path(target_path)
    source = Path(source_path)
    have, _ = _ids_and_lines(target)
    _, src_lines = _ids_and_lines(source)
    new = []
    for oid, raw in src_lines:
        if oid and oid not in have:
            new.append(raw)
            have.add(oid)                      # dedup intra-source aussi
    if new:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            for raw in new:
                f.write(raw + "\n")
    return {"added": len(new),
            "already_present": len(src_lines) - len(new),
            "source_total": len(src_lines)}


def main() -> None:
    p = argparse.ArgumentParser(description="Synchro de journal : fusionne (append-only, dedup par id).")
    p.add_argument("--from", dest="src", required=True, help="journal source (distant, copie, USB...)")
    p.add_argument("--to", dest="dst", default=config.JOURNAL_PATH, help="journal hote (defaut : config)")
    a = p.parse_args()
    r = merge_journal(a.dst, a.src)
    print(f"[sync] {r['added']} events ajoutes ({r['already_present']} deja presents, "
          f"{r['source_total']} dans la source) -> {a.dst}")


if __name__ == "__main__":
    main()
