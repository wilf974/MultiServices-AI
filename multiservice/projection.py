"""Projection SQLite reconstructible — P0 scaling (docs/SCALING-PROJECTIONS.md).

Le journal reste la VERITE ; la projection est un `fold(journal)` memoise avec un WATERMARK
`(line_count, chain_head)`. Les fonctions pures (ici `search_pure`) restent l'ORACLE : `verify_projection`
recompute from scratch et compare un hash d'etat -> egalite = preuve. Le watermark est lie a
`integrity.chain_head` : si le prefixe du journal a change (tamper/reecriture), la tete diverge et l'update
incremental refuse -> REBUILD force (une projection ne propage jamais silencieusement une falsification).

P0 = materialisation + recherche lexicale + watermark + verify.
P1 (Phase 1) = FTS5 (trigram sur texte NORMALISE, accent-insensible) comme PREFILTRE sur-ensemble +
routage `recall`/`recent`/`brief` vers SQL (`recall_sql`/`recent_sql`/`brief_sql`). Les fonctions pures
de `memory` restent LE moteur semantique : le SQL ne fait que restreindre la liste d'events qu'on leur
donne (candidats FTS + toutes les corrections C3), d'ou l'egalite ORACLE par construction.
DIFFERE : sqlite-vec (binaire+re-score, decision 0407c17a), snapshots/as-of.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from . import integrity, memory
from .events import AetherEvent
from .journal import read_events
from .skills import _norm, _tokens

_COLS = "line_no,id,type,source,text,valid_from,valid_to,raw"
_SCHEMA = "2"                       # P1 : colonne raw + FTS5 trigram + valid_from normalise UTC


def _iso(dt):
    """ISO normalise UTC : rend les comparaisons SQL sur valid_from lexicographiquement correctes."""
    dt = memory._aware(dt)
    return dt.astimezone(timezone.utc).isoformat() if dt is not None else None


def _text(e: AetherEvent) -> str:
    return " ".join(x for x in (e.title, e.description, e.source) if x).strip()


def _row(line_no: int, e: AetherEvent, raw: str):
    return (line_no, e.id, e.type.value, e.source, _text(e), _iso(e.valid_from), _iso(e.valid_to), raw)


def search_pure(events: List[AetherEvent], term: str) -> List[str]:
    """ORACLE : recherche lexicale PURE (meme semantique que `Projection.search`). Insensible a la casse."""
    t = term.lower()
    return [e.id for e in events if t in _text(e).lower()]


class Projection:
    """Materialisation SQLite du journal, reconstructible a l'identique. `conn` expose pour les tests/CI."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        if self._get("schema") != _SCHEMA:               # base d'un schema anterieur (P0) : la projection
            self.conn.execute("DROP TABLE IF EXISTS events")      # est un derive -> on jette et on
            self.conn.execute("DROP TABLE IF EXISTS events_fts")  # reconstruira depuis le journal-verite
            self.conn.execute("DELETE FROM meta")
            self._set("schema", _SCHEMA)
        self.conn.execute("CREATE TABLE IF NOT EXISTS events ("
                          "line_no INTEGER PRIMARY KEY, id TEXT, type TEXT, source TEXT, "
                          "text TEXT, valid_from TEXT, valid_to TEXT, raw TEXT)")
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS events_fts "
                          "USING fts5(ntext, tokenize='trigram')")   # trigram = parite sous-chaine avec _score
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

    def _insert(self, lines, events, start: int, n: int) -> None:
        self.conn.executemany(f"INSERT INTO events ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
                              [_row(i, events[i], lines[i]) for i in range(start, n)])
        self.conn.executemany("INSERT INTO events_fts (rowid, ntext) VALUES (?,?)",
                              [(i, _norm(memory._text(events[i]))) for i in range(start, n)])

    # --- (re)construction ---
    def rebuild(self, journal) -> int:
        """Fold complet depuis genesis. Idempotent."""
        lines, events, n = self._load(journal)
        self.conn.execute("DELETE FROM events")
        self.conn.execute("DELETE FROM events_fts")
        self._insert(lines, events, 0, n)
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
        self._insert(lines, events, wm_count, n)
        self._set("line_count", str(n))
        self._set("chain_head", integrity.chain_head(lines[:n]))
        self.conn.commit()
        return n - wm_count

    # --- prefiltre FTS (Phase 1) ---
    def _candidate_where(self, query: str):
        """Clause SQL selectionnant un SUR-ENSEMBLE des events a score lexical > 0 (`memory._score`).
        Meme normalisation (`_norm`) et memes tokens (`_tokens`) que le pur ; trigram = sous-chaine,
        donc 'moteur' attrape 'moteurs' comme le fait `t in low`. Requete sans token -> repli phrase
        (trigram si >= 3 chars, LIKE sinon) ; requete vide -> aucun candidat lexical."""
        toks = sorted(_tokens(query))
        if toks:
            match = " OR ".join('"%s"' % t.replace('"', '""') for t in toks)
            return "line_no IN (SELECT rowid FROM events_fts WHERE events_fts MATCH ?)", [match]
        qn = _norm(query).strip()
        if len(qn) >= 3:
            return ("line_no IN (SELECT rowid FROM events_fts WHERE events_fts MATCH ?)",
                    ['"%s"' % qn.replace('"', '""')])
        if qn:
            like = "%" + qn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            return "line_no IN (SELECT rowid FROM events_fts WHERE ntext LIKE ? ESCAPE '\\')", [like]
        return "0", []

    def events_for_recall(self, query: str) -> List[AetherEvent]:
        """Events a donner au `recall`/`topic_brief` PUR : candidats FTS + TOUTES les corrections
        (les index C3 — supersede par session, clotures ciblees — en ont besoin meme quand la
        correction ne matche pas la requete). Ordre journal preserve (stabilite du tri pur)."""
        where, params = self._candidate_where(query)
        cur = self.conn.execute(f"SELECT raw FROM events WHERE {where} OR type='correction' "
                                "ORDER BY line_no", params)
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    def events_window(self, start_iso: str, end_iso: str) -> List[AetherEvent]:
        """Events dont valid_from (normalise UTC) tombe dans [start, end]. Pour `recent` : la fenetre
        est le SEUL prefiltre (les compteurs du pur restent COMPLETS sur la fenetre)."""
        cur = self.conn.execute("SELECT raw FROM events WHERE valid_from >= ? AND valid_from <= ? "
                                "ORDER BY line_no", (start_iso, end_iso))
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

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


# --- routage Phase 1 : meme resultat que la fonction pure sur le journal entier (ORACLE) ---

def for_journal(journal, db_path: str | Path) -> Projection:
    """Ouvre (ou cree) la projection et la RATTRAPE sur le journal (update incremental ; rebuild
    force si prefixe change ou schema perime). Point d'entree des surfaces de lecture (MCP)."""
    p = Projection(db_path)
    p.update(journal)
    return p

def recall_sql(proj: Projection, query: str, **kw):
    """`memory.recall` servi par la projection : le FTS restreint la liste, le PUR decide de tout
    (scores, C3, tri, snippets). LECTURE SEULE."""
    return memory.recall(proj.events_for_recall(query), query, **kw)


def recent_sql(proj: Projection, days: int = 7, now=None, **kw):
    """`memory.recent` servi par la projection : prefiltre = la fenetre temporelle seule (compteurs
    complets). `now` est fige ICI pour que prefiltre et pur voient le meme instant. LECTURE SEULE."""
    n = memory._aware(now) or datetime.now(timezone.utc)
    cutoff = n - timedelta(days=days)
    evs = proj.events_window(cutoff.astimezone(timezone.utc).isoformat(),
                             n.astimezone(timezone.utc).isoformat())
    return memory.recent(evs, days=days, now=n, **kw)


def brief_sql(proj: Projection, query: str, k: int = 5, as_of=None):
    """`memory.topic_brief` servi par la projection (compose recall : memes candidats). LECTURE SEULE."""
    return memory.topic_brief(proj.events_for_recall(query), query, k=k, as_of=as_of)


def verify_projection(journal, proj: Projection) -> bool:
    """ORACLE de reconstruction : recompute la projection from scratch (en memoire) et compare le hash
    d'etat. Egalite = preuve que l'etat incremental == le fold complet. A faire tourner EN CI."""
    fresh = Projection(":memory:")
    fresh.rebuild(journal)
    return proj.state_hash() == fresh.state_hash()
