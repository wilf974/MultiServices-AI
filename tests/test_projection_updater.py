"""Phase 2 scaling — updater incremental (docs/SCALING-PROJECTIONS.md §4).

La projection est rattrapee HORS du chemin de lecture : commande `project` one-shot post-append
ou tail-watcher (poll). Invariants testes : run_once rattrape (et reste l'egal du batch, ORACLE),
status mesure le retard SANS rien avancer, watch applique au fil de l'eau et ne relit pas le
journal quand rien n'a change (stat), tamper pendant watch -> rebuild (jamais masque), et
l'updater N'ECRIT JAMAIS le journal (la verite reste intouchee)."""
from multiservice import project, projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(title, source="project:demo"):
    return AetherEvent(type=EventType.NOTE, title=title, source=source)


def test_run_once_rattrape_le_journal(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un"), _ev("deux")])
    r = project.run_once(journal, db)
    assert r["applied"] == 2 and r["line_count"] == 2
    append_events(journal, [_ev("trois")])
    r = project.run_once(journal, db)
    assert r["applied"] == 1 and r["line_count"] == 3
    assert projection.verify_projection(journal, projection.Projection(db))   # ORACLE


def test_run_once_sans_nouveaute_est_noop(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un")])
    project.run_once(journal, db)
    assert project.run_once(journal, db)["applied"] == 0


def test_status_mesure_le_retard_sans_avancer(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un"), _ev("deux")])
    project.run_once(journal, db)
    append_events(journal, [_ev("trois")])
    s = project.status(journal, db)
    assert s["journal_lines"] == 3 and s["projected"] == 2 and s["lag"] == 1
    assert s["fresh"] is False
    s2 = project.status(journal, db)                       # status est en LECTURE : rien n'avance
    assert s2 == s
    project.run_once(journal, db)
    s3 = project.status(journal, db)
    assert s3["lag"] == 0 and s3["fresh"] is True and s3["prefix_ok"] is True


def test_status_detecte_prefixe_falsifie(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("original")])
    project.run_once(journal, db)
    evs = read_events(journal)
    tampered = evs[0].model_copy(update={"title": "FALSIFIE"})
    journal.write_text(tampered.model_dump_json() + "\n", encoding="utf-8")
    s = project.status(journal, db)
    assert s["prefix_ok"] is False and s["fresh"] is False


def test_watch_applique_les_appends_au_fil_de_l_eau(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un")])

    def fake_sleep(_):                                     # le monde bouge entre deux polls
        append_events(journal, [_ev("pendant-le-watch")])

    total = project.watch(journal, db, interval=0, max_loops=2, sleep=fake_sleep)
    assert total == 2                                      # 1 (rattrapage) + 1 (append vu au poll suivant)
    p = projection.Projection(db)
    assert p.search("pendant-le-watch") != []
    assert projection.verify_projection(journal, p)


def test_watch_ne_relit_pas_le_journal_inchange(tmp_path, monkeypatch):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un")])
    calls = []
    orig = projection.Projection.update
    monkeypatch.setattr(projection.Projection, "update",
                        lambda self, j: calls.append(1) or orig(self, j))
    project.watch(journal, db, interval=0, max_loops=5, sleep=lambda _: None)
    assert len(calls) == 1                                 # rattrapage initial puis stat inchange -> aucune relecture


def test_watch_tamper_force_rebuild(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("original alpha"), _ev("original beta")])

    def tamper(_):                                         # reecriture du PREFIXE entre deux polls
        evs = read_events(journal)
        bad = evs[0].model_copy(update={"title": "FALSIFIE gamma"})
        journal.write_text(bad.model_dump_json() + "\n" + evs[1].model_dump_json() + "\n",
                           encoding="utf-8")

    project.watch(journal, db, interval=0, max_loops=2, sleep=tamper)
    p = projection.Projection(db)
    assert p.search("FALSIFIE") != [] and p.search("alpha") == []
    assert projection.verify_projection(journal, p)


def test_updater_n_ecrit_jamais_le_journal(tmp_path):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un"), _ev("deux")])
    before = journal.read_bytes()
    project.run_once(journal, db)
    project.status(journal, db)
    project.watch(journal, db, interval=0, max_loops=3, sleep=lambda _: None)
    assert journal.read_bytes() == before                  # la verite reste intouchee


def test_main_update_status_verify(tmp_path, capsys):
    journal = tmp_path / "j.jsonl"
    db = tmp_path / "proj.db"
    append_events(journal, [_ev("un")])
    args = ["--journal", str(journal), "--db", str(db)]
    project.main(args)                                     # defaut = update one-shot
    out = capsys.readouterr().out
    assert "applied=1" in out
    project.main(args + ["--status"])
    assert "lag=0" in capsys.readouterr().out
    project.main(args + ["--verify"])
    assert "OK" in capsys.readouterr().out
