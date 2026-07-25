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
Canal VECTORIEL BINAIRE (decision 0407c17a, LOCAL ONLY) : table `vecs(id, bits)` = quantization
binaire (128 o/vecteur bge-m3) synchronisee depuis l'EmbeddingStore (qui GARDE les float32, verite
reconstructible). Le top-M Hamming n'est qu'un PREFILTRE de plus (union candidats FTS + top-M +
corrections) ; le re-score float32 reste dans `memory.recall_semantic` (pur). Approximation assumee
et CALIBREE SUR LE REEL (2379 vecteurs bge-m3, 100 requetes) : recall@10 dans le top-M binaire =
96.3% a M=40, 99.1% a M=80 (defaut), 99.5% a M=120 ; prefiltre 2.9ms vs 182ms cosinus exact (x63).
`evict` (crypto-shredding) PROPAGE au sync (les bits derivent du clair).
Phase 3 (snapshots/as-of, design par.3) : etat ACTIF par TEMPS VALIDE. Oracle pur `memory.as_of` ;
table `closures` (fold des clotures ciblees, couverte par state_hash/verify) ; `take_snapshot(T)`
fige l'etat actif (refigeable, ne derive que du journal) ; `as_of_sql` = snapshot le plus proche
<= T + delta par temps valide + overlay (corrections + cibles) -> sur-ensemble par construction,
le pur tranche (egalite oracle). Correction tardive refletee SANS rebuild ; rebuild force (tamper)
-> snapshots PURGES (jamais d'etat fige derive d'un prefixe inconnu).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from . import integrity, memory
from .events import AetherEvent, EventType
from .journal import read_events
from .semantic import hamming, pack_bits
from .skills import _norm, _tokens

_COLS = "line_no,id,type,source,text,valid_from,valid_to,raw,session_id,turn_id"
# v5 : session_id + turn_id indexes -> acces CIBLE (why/replay/reasoning/forecast) au lieu de
# relire le journal entier. Un changement de schema est sans risque : la projection est un DERIVE,
# elle se reconstruit depuis le journal-verite.
_SCHEMA = "5"                       # v4 : closures + snapshots (as-of) ; v3 : vecs ; v2 : raw + FTS5 + UTC


def _iso(dt):
    """ISO normalise UTC : rend les comparaisons SQL sur valid_from lexicographiquement correctes."""
    dt = memory._aware(dt)
    return dt.astimezone(timezone.utc).isoformat() if dt is not None else None


def _text(e: AetherEvent) -> str:
    return " ".join(x for x in (e.title, e.description, e.source) if x).strip()


def _row(line_no: int, e: AetherEvent, raw: str):
    return (line_no, e.id, e.type.value, e.source, _text(e), _iso(e.valid_from), _iso(e.valid_to),
            raw, e.data.get("session_id"), e.data.get("turn_id"))


def search_pure(events: List[AetherEvent], term: str) -> List[str]:
    """ORACLE : recherche lexicale PURE (meme semantique que `Projection.search`). Insensible a la casse."""
    t = term.lower()
    return [e.id for e in events if t in _text(e).lower()]


class Projection:
    """Materialisation SQLite du journal, reconstructible a l'identique. `conn` expose pour les tests/CI."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = db_path
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)   # sqlite ne cree pas les parents
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        if self._get("schema") != _SCHEMA:               # base d'un schema anterieur : la projection
            self.conn.execute("DROP TABLE IF EXISTS events")      # est un derive -> on jette et on
            self.conn.execute("DROP TABLE IF EXISTS events_fts")  # reconstruira depuis le journal-verite
            self.conn.execute("DROP TABLE IF EXISTS vecs")        # (et le store d'embeddings pour vecs)
            self.conn.execute("DROP TABLE IF EXISTS closures")
            self.conn.execute("DROP TABLE IF EXISTS snapshots")
            self.conn.execute("DROP TABLE IF EXISTS snapshot_state")
            self.conn.execute("DELETE FROM meta")
            self._set("schema", _SCHEMA)
        self.conn.execute("CREATE TABLE IF NOT EXISTS events ("
                          "line_no INTEGER PRIMARY KEY, id TEXT, type TEXT, source TEXT, "
                          "text TEXT, valid_from TEXT, valid_to TEXT, raw TEXT, "
                          "session_id TEXT, turn_id TEXT)")
        # Index de PREFILTRE : c'est ce qui evite de relire le journal entier par appel.
        for idx, col in (("ix_ev_session", "session_id"), ("ix_ev_turn", "turn_id"),
                         ("ix_ev_type", "type"), ("ix_ev_vf", "valid_from")):
            self.conn.execute("CREATE INDEX IF NOT EXISTS %s ON events (%s)" % (idx, col))
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS events_fts "
                          "USING fts5(ntext, tokenize='trigram')")   # trigram = parite sous-chaine avec _score
        self.conn.execute("CREATE TABLE IF NOT EXISTS vecs (id TEXT PRIMARY KEY, bits BLOB)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS closures ("     # fold des clotures ciblees
                          "target_id TEXT, corr_id TEXT, PRIMARY KEY (target_id, corr_id))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS snapshots ("    # etats actifs figes (as-of)
                          "ts TEXT PRIMARY KEY, line_count INTEGER, created_at TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS snapshot_state ("
                          "ts TEXT, id TEXT, PRIMARY KEY (ts, id))")
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
        trous = ",".join("?" * len(_COLS.split(",")))     # derive de _COLS : ajouter une colonne
        self.conn.executemany(f"INSERT INTO events ({_COLS}) VALUES ({trous})",   # ne casse plus rien
                              [_row(i, events[i], lines[i]) for i in range(start, n)])
        self.conn.executemany("INSERT INTO events_fts (rowid, ntext) VALUES (?,?)",
                              [(i, _norm(memory._text(events[i]))) for i in range(start, n)])
        pairs = [(t, events[i].id) for i in range(start, n)
                 if events[i].type == EventType.CORRECTION
                 and isinstance(events[i].data.get("closes"), list)
                 for t in events[i].data["closes"] if isinstance(t, str) and t]
        if pairs:                                        # fold des clotures ciblees (as-of, Phase 3)
            self.conn.executemany("INSERT OR IGNORE INTO closures (target_id, corr_id) VALUES (?,?)", pairs)

    # --- (re)construction ---
    def rebuild(self, journal) -> int:
        """Fold complet depuis genesis. Idempotent. Purge aussi les SNAPSHOTS : un etat fige
        derive d'un prefixe desormais inconnu (tamper) ne doit pas survivre — un snapshot est
        refigeable a l'identique via `take_snapshot(ts)` (il ne derive que du journal)."""
        lines, events, n = self._load(journal)
        self.conn.execute("DELETE FROM events")
        self.conn.execute("DELETE FROM events_fts")
        self.conn.execute("DELETE FROM closures")
        self.conn.execute("DELETE FROM snapshots")
        self.conn.execute("DELETE FROM snapshot_state")
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

    def events_by_session(self, session_id: str) -> List[AetherEvent]:
        """Events d'UNE session, ordre journal. Prefiltre EXACT : `replay`, `reasoning` et
        `forecast` ne regardent que cette session — y compris leur index C3, qui est par session."""
        cur = self.conn.execute("SELECT raw FROM events WHERE session_id=? ORDER BY line_no",
                                (session_id,))
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    def events_by_turn(self, turn_id: str) -> List[AetherEvent]:
        """Events d'UN tour, ordre journal. Prefiltre EXACT : `why` ne regarde que ce tour."""
        cur = self.conn.execute("SELECT raw FROM events WHERE turn_id=? ORDER BY line_no",
                                (turn_id,))
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    def events_by_types(self, types, since_iso: str = None) -> List[AetherEvent]:
        """Events des types demandes, ordre journal. Prefiltre EXACT quand la fonction pure ne
        regarde que ces types (`lessons` = correction+faits perimables, `usage` = token_usage...).
        `since_iso` ajoute la borne temporelle : pour une vue fenetree (`project_review(days=N)`),
        c'est elle qui coupe vraiment — les types couvrent l'essentiel du journal."""
        types = list(types)
        if not types:
            return []
        trous = ",".join("?" * len(types))
        sql = "SELECT raw FROM events WHERE type IN (%s)" % trous
        params = list(types)
        if since_iso:
            sql += " AND valid_from >= ?"            # `_iso` normalise UTC -> comparaison lexicale sure
            params.append(since_iso)
        cur = self.conn.execute(sql + " ORDER BY line_no", params)
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    def session_of(self, event_id: str):
        """Session d'un event, sans charger l'event (une seule colonne)."""
        r = self.conn.execute("SELECT session_id FROM events WHERE id=? LIMIT 1",
                              (event_id,)).fetchone()
        return r[0] if r else None

    def stats(self) -> dict:
        """Agregats SANS charger un seul event (COUNT/MAX/DISTINCT). `health` relisait 2765 lignes
        pour compter : c'etait le gaspillage le plus net des onze outils."""
        n, dernier = self.conn.execute(
            "SELECT COUNT(*), MAX(valid_from) FROM events").fetchone()
        sources = self.conn.execute(
            "SELECT COUNT(DISTINCT source) FROM events WHERE source IS NOT NULL AND source<>''"
        ).fetchone()[0]
        return {"count": n or 0, "last_valid_from": dernier, "sources": sources or 0}

    def events_window(self, start_iso: str, end_iso: str) -> List[AetherEvent]:
        """Events dont valid_from (normalise UTC) tombe dans [start, end]. Pour `recent` : la fenetre
        est le SEUL prefiltre (les compteurs du pur restent COMPLETS sur la fenetre)."""
        cur = self.conn.execute("SELECT raw FROM events WHERE valid_from >= ? AND valid_from <= ? "
                                "ORDER BY line_no", (start_iso, end_iso))
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    # --- canal vectoriel binaire (decision 0407c17a, local only) ---
    def sync_vectors(self, store) -> dict:
        """Reconcilie `vecs` avec l'EmbeddingStore (verite float32) : ajoute les bits manquants,
        RETIRE ceux dont le vecteur a disparu (evict / crypto-shredding : les bits derivent du
        clair efface, ils ne doivent pas survivre)."""
        vecs = store.load()
        have = {r[0] for r in self.conn.execute("SELECT id FROM vecs")}
        add = [(i, pack_bits(v)) for i, v in vecs.items() if i not in have]
        gone = [(i,) for i in have if i not in vecs]
        self.conn.executemany("INSERT INTO vecs (id, bits) VALUES (?,?)", add)
        self.conn.executemany("DELETE FROM vecs WHERE id=?", gone)
        self.conn.commit()
        return {"added": len(add), "removed": len(gone), "total": len(vecs)}

    def topk_hamming(self, qbits: bytes, m: int) -> List[str]:
        """Les M ids les plus proches en Hamming (XOR+popcount, brute-force : millisecondes a
        notre echelle, 128 o/vecteur). PREFILTRE approximatif, jamais decisionnaire."""
        rows = self.conn.execute("SELECT id, bits FROM vecs").fetchall()
        return [i for _, i in sorted((hamming(qbits, b), i) for i, b in rows)[:m]]

    def events_for_semantic(self, query: str, ids: List[str]) -> List[AetherEvent]:
        """Events a donner a `recall_semantic` PUR : candidats FTS (canal lexical, sur-ensemble
        exact) + top-M binaire (canal semantique, approx) + corrections C3. Ordre journal."""
        where, params = self._candidate_where(query)
        in_ids = ""
        if ids:
            in_ids = " OR id IN (%s)" % ",".join("?" for _ in ids)
        cur = self.conn.execute(f"SELECT raw FROM events WHERE {where} OR type='correction'{in_ids} "
                                "ORDER BY line_no", params + list(ids))
        return [AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()]

    # --- snapshots + as-of (Phase 3) ---
    def take_snapshot(self, at) -> int:
        """Fige l'etat ACTIF au temps valide `at` (oracle pur `memory.as_of` sur tout le journal
        projete, connaissance ACTUELLE des clotures). Refigeable a l'identique (ne derive que du
        journal) ; `line_count` = watermark courant (provenance). Retourne le nb d'ids figes."""
        iso = _iso(at)
        evs = [AetherEvent.model_validate_json(r[0])
               for r in self.conn.execute("SELECT raw FROM events ORDER BY line_no").fetchall()]
        ids = [e.id for e in memory.as_of(evs, at)]
        self.conn.execute("DELETE FROM snapshot_state WHERE ts=?", (iso,))
        self.conn.execute("INSERT OR REPLACE INTO snapshots (ts, line_count, created_at) "
                          "VALUES (?,?,?)",
                          (iso, int(self._get("line_count", "0")),
                           datetime.now(timezone.utc).isoformat()))
        self.conn.executemany("INSERT INTO snapshot_state (ts, id) VALUES (?,?)",
                              [(iso, i) for i in ids])
        self.conn.commit()
        return len(ids)

    # --- requetes ---
    def search(self, term: str) -> List[str]:
        cur = self.conn.execute("SELECT id FROM events WHERE lower(text) LIKE ? ORDER BY line_no",
                                (f"%{term.lower()}%",))
        return [r[0] for r in cur.fetchall()]

    def state_hash(self) -> str:
        """Hash deterministe du row-set (preuve d'egalite incremental vs batch). Ignore l'ordre
        d'insertion. Couvre events + closures (derives du journal) ; PAS les snapshots (etat
        d'exploitation fige par l'operateur, pas un fold — verify doit passer avec ou sans)."""
        h = hashlib.sha256()
        for r in self.conn.execute(f"SELECT {_COLS} FROM events ORDER BY line_no").fetchall():
            h.update(json.dumps(r, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for r in self.conn.execute("SELECT target_id, corr_id FROM closures "
                                   "ORDER BY target_id, corr_id").fetchall():
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


def recall_semantic_sql(proj: Projection, query: str, embedder, store, m: int = 80, **kw):
    """`memory.recall_semantic` servi par la projection : une seule passe d'embedding (le qvec du
    prefiltre Hamming est REUTILISE au re-score float32 du pur). M (>> k) borne l'approximation
    (defaut 80 = 99.1% de recall@10 mesure sur le corpus reel, re-score ~6ms) ;
    M >= corpus indexe -> egalite oracle par construction. LECTURE SEULE."""
    qvec = embedder.embed([query])[0]
    ids = proj.topk_hamming(pack_bits(qvec), m)
    return memory.recall_semantic(proj.events_for_semantic(query, ids), query, embedder, store,
                                  qvec=qvec, **kw)


def brief_sql(proj: Projection, query: str, k: int = 5, as_of=None):
    """`memory.topic_brief` servi par la projection (compose recall : memes candidats). LECTURE SEULE."""
    return memory.topic_brief(proj.events_for_recall(query), query, k=k, as_of=as_of)


def why_sql(proj: Projection, turn_id: str, **kw):
    """`memory.why` servi par la projection : prefiltre EXACT sur le tour. LECTURE SEULE."""
    return memory.why(proj.events_by_turn(turn_id), turn_id, **kw)


def replay_sql(proj: Projection, session_id: str, digest: bool = True, **kw):
    """`memory.replay_session` / `session_digest` servis par la projection. LECTURE SEULE."""
    evs = proj.events_by_session(session_id)
    return (memory.session_digest(evs, session_id) if digest
            else memory.replay_session(evs, session_id, **kw))


def reasoning_sql(proj: Projection, session_id: str, **kw):
    """`memory.reasoning_chain` servi par la projection. LECTURE SEULE."""
    return memory.reasoning_chain(proj.events_by_session(session_id), session_id, **kw)


def forecast_sql(proj: Projection, session_id: str = None, **kw):
    """`preheat.forecast_next_turn` servi par la projection : la projection d'un prochain tour ne
    regarde que SA session. Sans session_id, on ne peut pas prefiltrer (repli appelant)."""
    from . import preheat
    return preheat.forecast_next_turn(proj.events_by_session(session_id), session_id=session_id, **kw)


def _types_lecons() -> List[str]:
    """Types que `lessons_learned` regarde REELLEMENT : corrections, decisions, et les faits
    qu'une correction peut perimer (`_FACT_TYPES`, qui inclut completion et tool_result).
    Derive des ensembles du code, jamais recopie a la main : un oracle a deja pris en defaut
    une liste devinee (24/07)."""
    return sorted({"correction", "decision"} | {t.value for t in memory._FACT_TYPES})


def _types_revue() -> List[str]:
    """Types que la curation et la revue de projet regardent : faits soumis a curation,
    corrections, et faits perimables (les vues composent `lessons_learned`)."""
    from . import curator
    return sorted({t.value for t in curator.CURATED_TYPES} | {"correction"}
                  | {t.value for t in memory._FACT_TYPES})


def lessons_sql(proj: Projection, **kw):
    """`memory.lessons_learned` servi par la projection. LECTURE SEULE."""
    return memory.lessons_learned(proj.events_by_types(_types_lecons()), **kw)


def curation_sql(proj: Projection, **kw):
    """`curator.curation_report` servi par la projection. LECTURE SEULE."""
    from . import curator
    return curator.curation_report(proj.events_by_types(_types_revue()), **kw)


def project_review_sql(proj: Projection, project: str, days: int = None, now=None, **kw):
    """`memory.project_review` servi par la projection. Avec `days`, la FENETRE est le vrai
    discriminant (les types couvrent l'essentiel du journal) ; le pur coupe lui aussi sur
    valid_from d'abord, donc prefiltrer dessus reste EXACT. `now` est fige ICI pour que le
    prefiltre et le pur voient le meme instant. LECTURE SEULE."""
    n = memory._aware(now) or datetime.now(timezone.utc)
    depuis = None
    if days is not None:
        depuis = (n - timedelta(days=days)).astimezone(timezone.utc).isoformat()
    evs = proj.events_by_types(_types_revue(), since_iso=depuis)
    return memory.project_review(evs, project, days=days, now=n, **kw)


def usage_sql(proj: Projection, **kw):
    """`memory.reuse_stats` servi par la projection : seuls les TOKEN_USAGE portent le signal."""
    return memory.reuse_stats(proj.events_by_types(["token_usage"]), **kw)


def replay_event_sql(proj: Projection, event_id: str, depth: int = 3, **kw):
    """`memory.replay_event` servi par la projection : la chaine causale remonte la SESSION de
    l'event focus -> une requete pour trouver la session, une pour la charger. LECTURE SEULE."""
    sid = proj.session_of(event_id)
    if sid is None:                                   # event inconnu : le pur repond deja proprement
        return memory.replay_event([], event_id, depth=depth, **kw)
    return memory.replay_event(proj.events_by_session(sid), event_id, depth=depth, **kw)


def index_status_sql(proj: Projection, vecs: dict, **kw):
    """`memory.index_coverage` servi par la projection : seuls les types INDEXABLES comptent."""
    types = sorted(t.value for t in memory._INDEXABLE_TYPES)
    return memory.index_coverage(proj.events_by_types(types), vecs, **kw)


def briefing_today_sql(proj: Projection, now=None):
    """`memory.briefing_today` servi par la projection : une JOURNEE, donc la fenetre suffit.
    `now` est fige ICI pour que prefiltre et pur voient le meme instant."""
    n = memory._aware(now) or datetime.now(timezone.utc)
    debut = n.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    evs = proj.events_window(debut.isoformat(), n.astimezone(timezone.utc).isoformat())
    return memory.briefing_today(evs, now=n)


def health_sql(proj: Projection, index: dict = None, now=None) -> dict:
    """`memory.health` sans charger un seul event : COUNT / MAX / DISTINCT. Les avertissements
    passent par `memory.avertissements_sante` — meme source de verite que le pur. LECTURE SEULE."""
    from datetime import datetime as _dt
    n = memory._aware(now) or datetime.now(timezone.utc)
    s = proj.stats()
    last = memory._aware(_dt.fromisoformat(s["last_valid_from"])) if s["last_valid_from"] else None
    avertissements = memory.avertissements_sante(last, bool(s["count"]), index, n)
    return {"available": True, "event_count": s["count"],
            "last_event_at": last.isoformat() if last else None, "sources": s["sources"],
            "degraded": bool(avertissements), "warnings": avertissements}


def as_of_sql(proj: Projection, at) -> List[AetherEvent]:
    """Etat actif au temps valide `at` servi par la projection (design par.3 : snapshot le plus
    proche <= at + DELTA + OVERLAY des corrections). Candidats = ids du snapshot + delta par
    TEMPS VALIDE (valid_from dans (ts, at] — pas par ligne : un event retro/futur-date appende
    tot reste attrape) + toutes les corrections + leurs CIBLES (une cloture elle-meme close
    ressuscite sa cible : la cible doit rester candidate). Sur-ensemble de l'etat actif par
    construction (les clotures ne font qu'avancer) -> le PUR `memory.as_of` tranche et l'egalite
    oracle tient. Sans snapshot <= at : fold pur sur toute la table. LECTURE SEULE."""
    asof = memory._aware(at) or datetime.now(timezone.utc)
    iso = _iso(asof)
    row = proj.conn.execute("SELECT ts FROM snapshots WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                            (iso,)).fetchone()
    if row is None:
        cur = proj.conn.execute("SELECT raw FROM events ORDER BY line_no")
    else:
        cur = proj.conn.execute(
            "SELECT raw FROM events WHERE id IN (SELECT id FROM snapshot_state WHERE ts=?) "
            "OR (valid_from > ? AND valid_from <= ?) OR type='correction' "
            "OR id IN (SELECT target_id FROM closures) ORDER BY line_no",
            (row[0], row[0], iso))
    return memory.as_of([AetherEvent.model_validate_json(r[0]) for r in cur.fetchall()], asof)


def verify_projection(journal, proj: Projection) -> bool:
    """ORACLE de reconstruction : recompute la projection from scratch (en memoire) et compare le hash
    d'etat. Egalite = preuve que l'etat incremental == le fold complet. A faire tourner EN CI."""
    fresh = Projection(":memory:")
    fresh.rebuild(journal)
    return proj.state_hash() == fresh.state_hash()


def pitfalls_sql(proj: Projection, **kw):
    """`memory.pitfalls` servi par la projection : prefiltre par type, tres selectif (les pieges
    sont rares par nature, c'est ce qui fait leur valeur). LECTURE SEULE."""
    return memory.pitfalls(proj.events_by_types(["pitfall", "correction"]), **kw)


def resume_sql(proj: Projection, project: str, days: int = 14, **kw):
    """`memory.resume` servi par la projection. La vue compose pieges + sante + revue + recent +
    revisions : on charge donc les types de la revue UNION les pieges, et on borne par la fenetre
    quand elle est donnee (c'est elle qui coupe vraiment). LECTURE SEULE."""
    n = memory._aware(kw.pop("now", None)) or datetime.now(timezone.utc)
    depuis = (n - timedelta(days=days)).astimezone(timezone.utc).isoformat() if days else None
    types = sorted(set(_types_revue()) | {"pitfall"})
    # Les pieges ne se perimant que par cloture CIBLEE, ils doivent rester visibles hors fenetre :
    # un garde-fou ancien mord toujours. On les charge donc SANS borne temporelle.
    evs = proj.events_by_types(types, since_iso=depuis) + (
        proj.events_by_types(["pitfall"]) if depuis else [])
    vus, uniques = set(), []
    for e in evs:
        if e.id not in vus:
            vus.add(e.id)
            uniques.append(e)
    return memory.resume(uniques, project, days=days, now=n, **kw)
