"""P0 scaling — projection SQLite reconstructible (docs/SCALING-PROJECTIONS.md).

Invariants testes : ORACLE (projection == fonction pure), incremental == batch (meme state_hash),
watermark lie a chain_head (prefixe falsifie -> rebuild force), verify_projection (divergence detectee)."""
from multiservice import projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(title, source="project:demo", desc=""):
    return AetherEvent(type=EventType.NOTE, title=title, description=desc, source=source)


def _proj(tmp):
    return projection.Projection(tmp / "proj.db")


def test_oracle_search_egale_fonction_pure(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("moteur NEMA-17"), _ev("servo MG996R"), _ev("le moteur cale")])
    p = _proj(tmp_path); p.rebuild(journal)
    evs = read_events(journal)
    for term in ("moteur", "servo", "NEMA", "absent"):
        assert p.search(term) == projection.search_pure(evs, term)   # ORACLE


def test_incremental_egale_batch(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("un"), _ev("deux")])
    inc = _proj(tmp_path); inc.rebuild(journal)                      # etat initial
    append_events(journal, [_ev("trois"), _ev("quatre")])           # le journal grandit
    inc.update(journal)                                             # mise a jour incrementale
    batch = projection.Projection(tmp_path / "batch.db"); batch.rebuild(journal)
    assert inc.state_hash() == batch.state_hash()                   # incremental == batch


def test_update_sans_nouvelles_lignes_est_noop(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("un")])
    p = _proj(tmp_path); p.rebuild(journal)
    h = p.state_hash()
    assert p.update(journal) == 0 and p.state_hash() == h


def test_watermark_prefixe_falsifie_force_rebuild(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("original alpha"), _ev("original beta")])
    p = _proj(tmp_path); p.rebuild(journal)
    # falsification d'une ligne du PREFIXE (reecriture complete du fichier) :
    evs = read_events(journal)
    tampered = evs[0].model_copy(update={"title": "FALSIFIE gamma"})
    journal.write_text(tampered.model_dump_json() + "\n" + evs[1].model_dump_json() + "\n", encoding="utf-8")
    p.update(journal)                                              # chain_head diverge -> rebuild force
    assert p.search("FALSIFIE") == [tampered.id]                   # la projection reflete le nouveau contenu
    assert p.search("alpha") == []                                 # l'ancien a disparu (pas d'ajout aveugle)
    assert projection.verify_projection(journal, p)                # coherente avec un rebuild from scratch


def test_verify_projection_detecte_divergence(tmp_path):
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev("un"), _ev("deux")])
    p = _proj(tmp_path); p.rebuild(journal)
    assert projection.verify_projection(journal, p)                # coherente
    p.conn.execute("INSERT INTO events (line_no,id,type,source,text,valid_from,valid_to) "
                   "VALUES (99,'x','note','s','faux',NULL,NULL)"); p.conn.commit()
    assert not projection.verify_projection(journal, p)            # divergence detectee


def test_journal_vide(tmp_path):
    journal = tmp_path / "j.jsonl"
    p = _proj(tmp_path); p.rebuild(journal)
    assert p.search("x") == [] and projection.verify_projection(journal, p)
