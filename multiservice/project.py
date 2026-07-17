"""Updater incremental de la projection — Phase 2 scaling (docs/SCALING-PROJECTIONS.md §4).

La projection (index de LECTURE, jamais une verite) est rattrapee HORS du chemin de lecture :
  - one-shot   : `python -m multiservice.project` apres un append (run_once) ;
  - tail-watch : `python -m multiservice.project --watch` (poll ; le journal n'est RELU que si
    son stat (taille, mtime) a change — un poll a vide ne coute qu'un os.stat).

Le rebuild force sur prefixe divergent (tamper) est herite de `Projection.update` : le watcher ne
peut pas propager silencieusement une falsification, et une corruption au milieu du journal leve
(jamais masquee, convention `read_events`). Ce module N'ECRIT JAMAIS le journal.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Optional

from . import integrity
from .journal import read_events
from .projection import Projection, verify_projection


def _stat(journal) -> Optional[tuple]:
    """Empreinte de changement bon marche (taille, mtime ns). None si absent."""
    try:
        st = os.stat(str(journal))
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def run_once(journal, db_path) -> Dict:
    """Rattrape la projection sur le journal (incremental ; rebuild force si prefixe divergent)."""
    p = Projection(db_path)
    applied = p.update(journal)
    return {"applied": applied, "line_count": int(p._get("line_count", "0")),
            "chain_head": p._get("chain_head", "")}


def status(journal, db_path) -> Dict:
    """Retard de la projection vs journal. LECTURE SEULE : n'avance rien, ne rattrape rien."""
    lines = integrity._lines(journal)
    n = min(len(lines), len(read_events(journal)))         # meme convention 1:1 que Projection._load
    p = Projection(db_path)
    wm = int(p._get("line_count", "0"))
    prefix_ok = wm <= n and integrity.chain_head(lines[:wm]) == p._get("chain_head", "")
    return {"journal_lines": n, "projected": wm, "lag": n - wm,
            "prefix_ok": prefix_ok, "fresh": prefix_ok and n == wm}


def watch(journal, db_path, interval: float = 2.0, max_loops: Optional[int] = None,
          sleep=time.sleep) -> int:
    """Tail-watcher : poll le journal et applique les nouvelles lignes au fil de l'eau.
    `max_loops`/`sleep` injectables (tests). Retourne le nb total de lignes appliquees."""
    p = Projection(db_path)
    total = 0
    last: object = object()                                # != tout stat -> le 1er poll rattrape toujours
    loops = 0
    while max_loops is None or loops < max_loops:
        st = _stat(journal)
        if st != last:                                     # stat pris AVANT l'update : un append pendant
            total += p.update(journal)                     # l'update sera revu au poll suivant (no-op sinon)
            last = st
        loops += 1
        if max_loops is None or loops < max_loops:
            sleep(interval)
    return total


def main(argv=None) -> None:
    import argparse

    from . import config
    ap = argparse.ArgumentParser(description="Updater incremental de la projection SQLite (Phase 2).")
    ap.add_argument("--journal", default=config.JOURNAL_PATH)
    ap.add_argument("--db", default=config.PROJECTION_PATH)
    ap.add_argument("--status", action="store_true", help="retard de la projection (lecture seule)")
    ap.add_argument("--rebuild", action="store_true", help="fold complet depuis genesis")
    ap.add_argument("--verify", action="store_true", help="oracle : recompute from scratch et compare (CI)")
    ap.add_argument("--watch", action="store_true", help="tail-watcher (poll)")
    ap.add_argument("--interval", type=float, default=2.0, help="periode de poll du watch (s)")
    a = ap.parse_args(argv)
    if a.status:
        s = status(a.journal, a.db)
        tag = "FRESH" if s["fresh"] else ("TAMPER" if not s["prefix_ok"] else "STALE")
        print(f"[project] {tag} journal={s['journal_lines']} projete={s['projected']} lag={s['lag']}")
        return
    if a.rebuild:
        n = Projection(a.db).rebuild(a.journal)
        print(f"[project] rebuild : {n} lignes")
        return
    if a.verify:
        if verify_projection(a.journal, Projection(a.db)):
            print("[project] verify : OK (etat incremental == fold complet)")
            return
        print("[project] verify : DIVERGENCE (rebuild recommande)")
        raise SystemExit(1)
    if a.watch:
        print(f"[project] watch : journal={a.journal} interval={a.interval}s (Ctrl+C pour arreter)")
        watch(a.journal, a.db, interval=a.interval)
        return
    r = run_once(a.journal, a.db)
    print(f"[project] applied={r['applied']} line_count={r['line_count']} head={r['chain_head'][:16]}...")


if __name__ == "__main__":
    main()
