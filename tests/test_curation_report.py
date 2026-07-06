"""Rapport de curation planifie (lecture seule) : ecrit un .md date, ne mute PAS le journal."""
from datetime import datetime, timezone, timedelta

from multiservice import curation_report as cr
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def _ev(text, vf, typ=EventType.DECISION, sid="s", src="project:maison"):
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def test_run_ecrit_rapport_date_et_signale_action(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("meme decision exacte", NOW - timedelta(days=1)),
                            _ev("meme decision exacte", NOW - timedelta(hours=1))])
    before = [e.id for e in read_events(str(jp))]
    path, needs, counts = cr.run(str(jp), str(tmp_path / "out"), now=NOW)
    assert needs is True and counts["exact_duplicates"] == 1
    md = (tmp_path / "out" / "curation-20260706.md").read_text(encoding="utf-8")
    assert "--closes" in md and "memlog-http" in md          # cloture prete
    assert path.endswith("curation-20260706.md")
    # LECTURE SEULE : le journal n'a pas bouge
    assert [e.id for e in read_events(str(jp))] == before


def test_run_journal_propre_pas_d_action(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("adopter apache-2.0 pour la licence", NOW - timedelta(days=2))])
    _, needs, counts = cr.run(str(jp), str(tmp_path / "out"), now=NOW)
    assert needs is False and counts["exact_duplicates"] == 0
