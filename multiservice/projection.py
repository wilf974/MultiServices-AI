"""Projection SQLite reconstructible — P0 scaling (docs/SCALING-PROJECTIONS.md).

Le journal reste la VERITE ; la projection est un `fold(journal)` memoise avec un WATERMARK
`(line_count, chain_head)`. Les fonctions pures (ici `search_pure`) restent l'ORACLE : `verify_projection`
recompute from scratch et compare un hash d'etat -> egalite = preuve. Le watermark est lie a
`integrity.chain_head` : si le prefixe du journal a change (tamper/reecriture), la tete diverge et l'update
incremental refuse -> REBUILD force (une projection ne propage jamais silencieusement une falsification).

P0 = materialisation + recherche lexicale + watermark + verify. DIFFERE : FTS5/sqlite-vec, snapshots/as-of,
routage de `recall`/`recent`/`brief` vers SQL.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import List

from . import integrity
from .events import AetherEvent
from .journal import read_events

_COLS = "line_no,id,type,source,text,valid_from,valid_to"


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _text(e: AetherEvent) -> str:
    return " ".join(x for x in (e.title, e.description, e.source) if x).strip()


def _row(line_no: int, e: AetherEvent):
    return (line_no, e.id, e.type.value, e.source, _text(e), _iso(e.valid_from), _iso(e.valid_to))


def search_pure(events: List[AetherEvent], term: str) -> List[str]:
    """ORACLE : recherche lexicale PURE (meme semantique que `Projection.search`). Insensible a la casse."""
    t = term.lower()
    return [e.id for e in events if t in _text(e).lower()]


class Projection:
    """Materialisation SQLite du journal, reconstructible a l'identique. `conn` expose pour les tests/CI."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("CREATE TABLE IF NOT EXISTS events ("
                          "line_no INTEGER PRIMARY KEY, id TEXT, type TEXT, source TEXT, "
                          "text TEXT, valid_from TEXT, valid_to TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        self.conn.commit()

    # --- watermark ---
    def _get(self, k: str, default: str = "") -> str:
        r = self.conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def _set(self, k: str, v: str) -> None:
        self.conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    def _load(self, journal):
        lines = integrity._lines(journal)
        events = read_events(journal)
        n = min(len(lines), len(events))                 # 1:1 ligne<->event (ignore une derniere ligne partielle)
        return lines, events, n

    # --- (re)construction ---
    def rebuild(self, journal) -> int:
        """Fold complet depuis genesis. Idempotent."""
        lines, events, n = self._load(journal)
        self.conn.execute("DELETE FROM events")
        self.conn.executemany(f"INSERT INTO events ({_COLS}) VALUES (?,?,?,?,?,?,?)",
                              [_row(i, events[i]) for i in range(n)])
        self._set("line_count", str(n))
        self._set("chain_head", integrity.chain_head(lines[:n]))
        self.conn.commit()
        return n

    def update(self, journal) -> int:
        """Update incremental (lignes apres le watermark). Prefixe change (chain_head divergent) -> rebuild
        force. Retourne le nb de lignes ajoutees (ou reconstruites via rebuild)."""
        lines, events, n = self._load(journal)
        wm_count = int(self._get("line_count", "0"))
        wm_head = self._get("chain_head", "")
        if wm_count > n or integrity.chain_head(lines[:wm_count]) != wm_head:
            return self.rebuild(journal)                 # le prefixe a change -> on ne propage pas a l'aveugle
        if n == wm_count:
            return 0
        self.conn.executemany(f"INSERT INTO events ({_COLS}) VALUES (?,?,?,?,?,?,?)",
                              [_row(i, events[i]) for i in range(wm_count, n)])
        self._set("line_count", str(n))
        self._set("chain_head", integrity.chain_head(lines[:n]))
        self.conn.commit()
        return n - wm_count

    # --- requetes ---
    def search(self, term: str) -> List[str]:
        cur = self.conn.execute("SELECT id FROM events WHERE lower(text) LIKE ? ORDER BY line_no",
                                (f"%{term.lower()}%",))
        return [r[0] for r in cur.fetchall()]

    def state_hash(self) -> str:
        """Hash deterministe du row-set (preuve d'egalite incremental vs batch). Ignore l'ordre d'insertion."""
        cur = self.conn.execute(f"SELECT {_COLS} FROM events ORDER BY line_no")
        h = hashlib.sha256()
        for r in cur.fetchall():
            h.update(json.dumps(r, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return h.hexdigest()


def verify_projection(journal, proj: Projection) -> bool:
    """ORACLE de reconstruction : recompute la projection from scratch (en memoire) et compare le hash
    d'etat. Egalite = preuve que l'etat incremental == le fold complet. A faire tourner EN CI."""
    fresh = Projection(":memory:")
    fresh.rebuild(journal)
    return proj.state_hash() == fresh.state_hash()
