"""Phase 1 scaling — FTS5 + routage recall/recent/brief vers SQL (docs/SCALING-PROJECTIONS.md).

Invariants testes : ORACLE (resultat route == fonction pure sur le meme journal), le prefiltre FTS
est un SUR-ENSEMBLE des hits purs (accents, sous-chaines), les corrections C3 hors-candidats sont
toujours fournies (drapeau superseded identique), migration P0 -> P1 (schema) sans crash, et
l'update incremental garde le FTS synchrone."""
from datetime import datetime, timedelta, timezone

import sqlite3

from multiservice import memory, projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(title, type_=EventType.NOTE, source="project:demo", desc="", data=None):
    return AetherEvent(type=type_, title=title, description=desc, source=source, data=data or {})


def _proj(tmp, journal):
    p = projection.Projection(tmp / "proj.db")
    p.update(journal)
    return p


def _corpus(journal):
    """Journal realiste : accents, pluriels (sous-chaine), sessions, decisions + correction C3."""
    t0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
    evs = [
        _ev("le reacteur principal chauffe", data={"session_id": "s1"}),
        _ev("les moteurs pas-a-pas NEMA-17 calent", data={"session_id": "s1"}),
        _ev("choix du servo MG996R", type_=EventType.DECISION, data={"session_id": "s2"}),
        _ev("note sans rapport aucun", data={"session_id": "s3"}),
        _ev("réacteur : purge décidée", type_=EventType.DECISION, data={"session_id": "s1"}),
        _ev("finalement purge annulee", type_=EventType.CORRECTION, data={"session_id": "s1"}),
    ]
    evs = [e.model_copy(update={"valid_from": t0 + timedelta(hours=i)}) for i, e in enumerate(evs)]
    append_events(journal, evs)
    return evs


def test_prefiltre_fts_surensemble_des_hits_purs(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    for q in ("moteur", "reacteur", "réacteur", "servo MG996R", "purge", "absent-du-journal"):
        pure_hits = {e.id for e in evs if memory._score(q, memory._text(e)) > 0}
        cand = {e.id for e in p.events_for_recall(q)}
        assert pure_hits <= cand, f"prefiltre pas sur-ensemble pour {q!r}"


def test_oracle_recall_sql_egale_recall_pur(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    for q in ("moteur", "réacteur", "purge", "servo", "absent-du-journal", "le la"):
        assert projection.recall_sql(p, q) == memory.recall(evs, q)  # ORACLE
    # avec filtres
    assert (projection.recall_sql(p, "purge", type_="decision")
            == memory.recall(evs, "purge", type_="decision"))
    assert (projection.recall_sql(p, "moteur", source_prefix="project:demo")
            == memory.recall(evs, "moteur", source_prefix="project:demo"))


def test_correction_hors_candidats_donne_le_meme_drapeau_superseded(tmp_path):
    # la correction 'finalement purge annulee' ne contient PAS 'reacteur' : elle n'est pas un
    # candidat FTS de cette requete, mais recall doit quand meme marquer superseded (C3).
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    routed = projection.recall_sql(p, "reacteur")
    assert routed == memory.recall(evs, "reacteur")                  # ORACLE
    flagged = [h for h in routed if h["superseded"]]
    assert flagged, "la decision corrigee doit porter le drapeau superseded"


def test_oracle_recall_as_of(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    avant_correction = datetime(2026, 7, 1, 4, 30, tzinfo=timezone.utc)
    assert (projection.recall_sql(p, "purge", as_of=avant_correction)
            == memory.recall(evs, "purge", as_of=avant_correction))


def test_oracle_recent_sql_egale_recent_pur(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    now = datetime(2026, 7, 2, tzinfo=timezone.utc)
    for days in (1, 30):
        assert (projection.recent_sql(p, days=days, now=now)
                == memory.recent(evs, days=days, now=now))           # ORACLE
    assert (projection.recent_sql(p, days=30, now=now, source_prefix="project:demo", limit=2)
            == memory.recent(evs, days=30, now=now, source_prefix="project:demo", limit=2))
    # fenetre qui exclut tout
    ancien = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert projection.recent_sql(p, days=7, now=ancien) == memory.recent(evs, days=7, now=ancien)


def test_oracle_brief_sql_egale_brief_pur(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    for q in ("purge", "moteur", "absent-du-journal"):
        assert projection.brief_sql(p, q) == memory.topic_brief(evs, q)   # ORACLE


def test_update_incremental_garde_le_fts_synchrone(tmp_path):
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = _proj(tmp_path, journal)
    append_events(journal, [_ev("nouvelle turbine hydraulique", data={"session_id": "s9"})])
    p.update(journal)                                                # incremental
    evs = read_events(journal)
    assert projection.recall_sql(p, "turbine") == memory.recall(evs, "turbine")
    assert projection.recall_sql(p, "turbine")                        # et il y a bien un hit
    assert projection.verify_projection(journal, p)


def test_migration_schema_p0_sans_crash(tmp_path):
    # une base P0 (sans raw, sans FTS, sans version de schema) doit etre reconstruite, pas crasher
    db = tmp_path / "proj.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE events (line_no INTEGER PRIMARY KEY, id TEXT, type TEXT, "
                 "source TEXT, text TEXT, valid_from TEXT, valid_to TEXT)")
    conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO meta VALUES ('line_count','1')")
    conn.execute("INSERT INTO meta VALUES ('chain_head','tete-p0-perimee')")
    conn.commit(); conn.close()
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    p = projection.Projection(db)                                    # migration silencieuse
    p.update(journal)                                                # watermark efface -> rebuild
    evs = read_events(journal)
    assert projection.recall_sql(p, "moteur") == memory.recall(evs, "moteur")
    assert projection.verify_projection(journal, p)


def test_for_journal_ouvre_et_rattrape_le_journal(tmp_path):
    # le point d'entree de la surface MCP : ouvre (ou cree) la projection et la met a jour
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    _corpus(journal)
    p = projection.for_journal(journal, db)
    assert projection.recall_sql(p, "moteur") == memory.recall(read_events(journal), "moteur")
    append_events(journal, [_ev("pompe peristaltique", data={"session_id": "s9"})])
    p2 = projection.for_journal(journal, db)                         # nouvel appel = rattrapage
    avant = journal.read_bytes()
    assert projection.recall_sql(p2, "pompe") == memory.recall(read_events(journal), "pompe")
    assert projection.recall_sql(p2, "pompe")                        # et le hit est bien la
    assert journal.read_bytes() == avant                             # structurel : JAMAIS d'ecriture journal


def test_projection_cree_le_dossier_parent(tmp_path):
    # cas conteneur : ~/.aethercore n'existe pas encore la ou vit la projection (journal monte
    # ailleurs en :ro). sqlite ne cree pas les parents -> Projection doit le faire.
    journal = tmp_path / "j.jsonl"
    _corpus(journal)
    db = tmp_path / "pas" / "encore" / "la" / "proj.db"
    p = projection.for_journal(journal, db)
    assert projection.recall_sql(p, "moteur") == memory.recall(read_events(journal), "moteur")


def test_journal_vide_et_requete_vide(tmp_path):
    journal = tmp_path / "j.jsonl"
    p = _proj(tmp_path, journal)
    assert projection.recall_sql(p, "rien") == []
    _corpus(journal); p.update(journal)
    evs = read_events(journal)
    assert projection.recall_sql(p, "") == memory.recall(evs, "")    # requete vide
