"""Integrite du journal — chaine de hachage tamper-evident (« git de la cognition », littéral).

Chaque tete de chaine = SHA-256(tete_precedente + ligne) sur les LIGNES BRUTES du journal (les
octets sur le disque, pas une re-serialisation). Toute modification, suppression ou reordre change
la tete a partir de la ligne touchee. Des SCEAUX ({count, head, ts}, append-only dans
`<journal>.chainseal.jsonl`) servent d'ancres de confiance : `verify` recompute et LOCALISE la
falsification au premier sceau divergent.

PUR (les fonctions de chaine) ; IO au bord (lecture journal / sceaux). Non-invasif : ne touche ni
les evenements ni `append_events`. Constitutionnellement propre : c'est une fonction du journal.

Note de confiance : un attaquant qui falsifie le journal ET re-scelle localement defait la garde.
La vraie force vient de sceaux dans un DOMAINE SEPARE (repliques au central, horodates) — le
mecanisme est ici, la replication des sceaux est la couche suivante.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def running_heads(lines: List[str], genesis: str = "") -> List[str]:
    """Tete de chaine APRES chaque ligne. PUR. Liste vide -> []."""
    heads: List[str] = []
    h = genesis
    for ln in lines:
        h = hashlib.sha256((h + "\n" + ln).encode("utf-8")).hexdigest()
        heads.append(h)
    return heads


def chain_head(lines: List[str], genesis: str = "") -> str:
    """Tete de chaine du journal entier (= dernier `running_heads`, ou `genesis` si vide). PUR."""
    heads = running_heads(lines, genesis)
    return heads[-1] if heads else genesis


def verify(lines: List[str], seals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verifie les lignes contre des sceaux {count, head}. Retourne le PREMIER sceau divergent
    (localise la falsification) ou ok. PUR."""
    heads = running_heads(lines)
    for s in sorted(seals, key=lambda s: s["count"]):
        c = int(s["count"])
        actual = heads[c - 1] if 0 < c <= len(heads) else None
        if actual != s["head"]:
            return {"ok": False, "broken_at": c, "sealed_head": s["head"],
                    "actual_head": actual, "total_lines": len(lines)}
    return {"ok": True, "sealed_count": max((int(s["count"]) for s in seals), default=0),
            "total_lines": len(lines)}


# --- IO au bord ---

def _lines(path: str | Path) -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _seal_path(journal_path: str | Path) -> Path:
    return Path(str(journal_path) + ".chainseal.jsonl")


def load_seals(journal_path: str | Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in _lines(_seal_path(journal_path)):
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def seal(journal_path: str | Path, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Scelle l'etat courant : append {ts, count, head} au sidecar. Ancre de confiance. IO au bord."""
    lines = _lines(journal_path)
    rec = {"ts": (now or datetime.now(timezone.utc)).isoformat(),
           "count": len(lines), "head": chain_head(lines)}
    sp = _seal_path(journal_path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    with sp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def status(journal_path: str | Path) -> Dict[str, Any]:
    """Etat d'integrite : verification contre tous les sceaux enregistres. IO au bord."""
    lines = _lines(journal_path)
    seals = load_seals(journal_path)
    res = verify(lines, seals)
    res.update({"head": chain_head(lines), "seals": len(seals)})
    return res


def main() -> None:
    import argparse

    from . import config
    p = argparse.ArgumentParser(description="Integrite du journal (chaine de hachage tamper-evident).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--seal", action="store_true", help="sceller l'etat courant (ancre de confiance)")
    p.add_argument("--verify", action="store_true", help="verifier le journal contre les sceaux")
    a = p.parse_args()
    if a.seal:
        rec = seal(a.journal)
        print(f"[integrity] scelle : count={rec['count']} head={rec['head'][:16]}...")
        return
    r = status(a.journal)
    tag = "OK" if r["ok"] else "FALSIFICATION"
    extra = "" if r["ok"] else f" broken_at={r.get('broken_at')}"
    print(f"[{tag}] head={r['head'][:16]}... lignes={r['total_lines']} sceaux={r['seals']}{extra}")


if __name__ == "__main__":
    main()
