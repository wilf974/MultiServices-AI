"""Phase 3 scaling — snapshots + requete as-of (docs/SCALING-PROJECTIONS.md par.3 et 5).

Invariants testes (plan de test du design) :
  - as-of PUR : filtre par TEMPS VALIDE (valid_from/valid_to + clotures ciblees data.closes) ;
  - snapshot + delta + overlay corrections == fold as-of pur (ORACLE, egalite par construction) ;
  - correction C3 TARDIVE (retro-datee) : refletee par as-of SANS rebuild ;
  - rebuild force (tamper) -> snapshots purges (jamais d'etat fige derive d'un prefixe inconnu) ;
  - incremental == batch reste vrai avec la table des clotures (state_hash).
"""
from datetime import datetime, timezone

from multiservice import memory, projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def T(day, hour=12):
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def _ev(title, vf, vt=None, typ=EventType.NOTE, data=None, source="project:demo"):
    return AetherEvent(type=typ, title=title, source=source,
                       valid_from=vf, valid_to=vt, data=data or {})


def _corr(closes, vf, vt=None, session="curation-closures"):
    return _ev("cloture", vf, vt=vt, typ=EventType.CORRECTION,
               data={"closes": list(closes), "session_id": session})


def _proj(tmp, journal):
    p = projection.Projection(tmp / "proj.db")
    p.rebuild(journal)
    return p


# --- l'oracle PUR : memory.as_of ---

def test_as_of_pur_filtre_par_temps_valide():
    a = _ev("ouvert", T(1))                       # jamais clos -> actif partout apres T1
    b = _ev("borne", T(1), vt=T(5))               # clos explicitement a T5
    c = _ev("futur", T(9))                        # pas encore valide avant T9
    evs = [a, b, c]
    assert [e.id for e in memory.as_of(evs, T(3))] == [a.id, b.id]
    assert [e.id for e in memory.as_of(evs, T(5))] == [a.id, b.id]   # vt == as_of : encore valide (convention recall)
    assert [e.id for e in memory.as_of(evs, T(6))] == [a.id]
    assert [e.id for e in memory.as_of(evs, T(10))] == [a.id, c.id]


def test_as_of_pur_cloture_ciblee_exclut_puis_cloture_close_reactive():
    fait = _ev("fait conteste", T(1))
    corr = _corr([fait.id], T(4), vt=T(8))        # clot le fait a partir de T4... jusqu'a T8 (la
    evs = [fait, corr]                            # cloture est elle-meme close ensuite, C3)
    assert [e.id for e in memory.as_of(evs, T(2))] == [fait.id]           # avant la cloture
    ids_t5 = [e.id for e in memory.as_of(evs, T(5))]
    assert fait.id not in ids_t5                                          # clos par overlay
    assert corr.id in ids_t5                                              # la correction, elle, est active
    assert fait.id in [e.id for e in memory.as_of(evs, T(9))]             # cloture close -> le fait revit


# --- snapshot + delta + overlay == fold pur (ORACLE) ---

def test_snapshot_plus_delta_egale_fold_pur(tmp_path):
    journal = tmp_path / "j.jsonl"
    early_future = _ev("valide plus tard", T(9))            # appendu TOT mais valide a T9 (delta par
    append_events(journal, [                                # temps valide, pas par ligne)
        _ev("socle", T(1)),
        _ev("borne", T(2), vt=T(4)),
        early_future,
        _corr(["inconnu"], T(3)),                           # cloture d'un id absent : inerte
    ])
    p = _proj(tmp_path, journal)
    assert p.take_snapshot(T(5)) > 0                        # snapshot fige a T5
    append_events(journal, [_ev("apres snapshot", T(7))])   # le journal continue
    p.update(journal)
    evs = read_events(journal)
    for at in (T(3), T(5), T(6), T(8), T(10)):              # avant/au/apres le snapshot
        assert [e.id for e in projection.as_of_sql(p, at)] == \
               [e.id for e in memory.as_of(evs, at)]        # ORACLE : SQL == pur


def test_as_of_sql_sans_snapshot_egale_pur(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("a", T(1)), _ev("b", T(2), vt=T(3))])
    p = _proj(tmp_path, journal)
    evs = read_events(journal)
    for at in (T(2), T(4)):
        assert [e.id for e in projection.as_of_sql(p, at)] == \
               [e.id for e in memory.as_of(evs, at)]


def test_correction_tardive_refletee_sans_rebuild(tmp_path):
    journal = tmp_path / "j.jsonl"
    ancien = _ev("verite d'epoque", T(1))
    append_events(journal, [ancien, _ev("contexte", T(2))])
    p = _proj(tmp_path, journal)
    p.take_snapshot(T(6))                                       # le snapshot CONTIENT l'ancien fait
    tardive = _corr([ancien.id], T(3))                          # arrive MAINTENANT, retro-datee T3
    append_events(journal, [tardive])
    assert p.update(journal) == 1                               # incremental (1 ligne), PAS un rebuild
    assert p.conn.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1   # snapshot intact
    evs = read_events(journal)
    for at in (T(2), T(4), T(7)):                               # avant/apres la cloture retro-datee
        assert [e.id for e in projection.as_of_sql(p, at)] == \
               [e.id for e in memory.as_of(evs, at)]
    assert ancien.id not in [e.id for e in projection.as_of_sql(p, T(7))]        # overlay applique


def test_rebuild_force_purge_les_snapshots(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("original alpha", T(1)), _ev("original beta", T(2))])
    p = _proj(tmp_path, journal)
    p.take_snapshot(T(3))
    evs = read_events(journal)                                  # falsification du prefixe (cf. P0)
    tampered = evs[0].model_copy(update={"title": "FALSIFIE gamma"})
    journal.write_text(tampered.model_dump_json() + "\n" + evs[1].model_dump_json() + "\n",
                       encoding="utf-8")
    p.update(journal)                                           # chain_head diverge -> rebuild force
    assert p.conn.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0   # purge (etat fige
    fresh = read_events(journal)                                # derive d'un prefixe inconnu)
    assert [e.id for e in projection.as_of_sql(p, T(4))] == \
           [e.id for e in memory.as_of(fresh, T(4))]            # repli sans snapshot : toujours l'oracle


def test_incremental_egale_batch_avec_clotures(tmp_path):
    journal = tmp_path / "j.jsonl"
    fait = _ev("fait", T(1))
    append_events(journal, [fait])
    inc = _proj(tmp_path, journal)
    append_events(journal, [_corr([fait.id], T(2))])            # une cloture arrive apres coup
    inc.update(journal)
    batch = projection.Projection(tmp_path / "batch.db")
    batch.rebuild(journal)
    assert inc.state_hash() == batch.state_hash()               # la table des clotures suit l'invariant
    assert projection.verify_projection(journal, inc)
    assert inc.conn.execute("SELECT count(*) FROM closures").fetchone()[0] == 1   # la cloture est materialisee


def test_main_snapshot_et_as_of(tmp_path, capsys):
    from multiservice import project
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    fait = _ev("fait ancien", T(1))
    append_events(journal, [fait, _ev("contexte", T(2)), _corr([fait.id], T(4))])
    args = ["--journal", str(journal), "--db", str(db)]
    project.main(args + ["--snapshot", T(2).isoformat()])       # fige l'etat actif a T2 (rattrape avant)
    assert "snapshot" in capsys.readouterr().out
    project.main(args + ["--as-of", T(1, hour=0).isoformat()])  # avant tout : rien d'actif
    assert "actifs=0" in capsys.readouterr().out
    project.main(args + ["--as-of", T(3).isoformat()])          # fait + contexte (la cloture T4 pas encore la)
    assert "actifs=2" in capsys.readouterr().out
