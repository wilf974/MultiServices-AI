"""Journal de decisions du projet (dogfooding) : capture DECISION/CORRECTION/NOTE.

Contrat : make_event porte C2 (source) + C3 (valid_from) ; log() ecrit append-only ; une
CORRECTION de la MEME session perime une DECISION anterieure (visible via recall.superseded).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import EventType
from multiservice.journal import read_events
from multiservice.memory import recall
from multiservice.projlog import KINDS, log, make_event

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def test_make_event_types_et_c2_c3():
    for kind, typ in KINDS.items():
        ev = make_event(kind, f"texte {kind}", source="agent:claude", session_id="s", now=T0)
        assert ev.type == typ
        assert ev.source == "agent:claude"            # C2
        assert ev.valid_from is not None              # C3
        assert ev.data["session_id"] == "s"


def test_log_ecrit_append_only(tmp_path):
    jp = tmp_path / "journal.jsonl"
    log(jp, "decision", "Adopter Apache-2.0", session_id="licence", now=T0)
    log(jp, "note", "lessons_learned lira les corrections", source="agent:claude",
        session_id="roadmap", now=T0 + timedelta(minutes=1))
    evs = read_events(jp)
    assert len(evs) == 2
    assert {e.type for e in evs} == {EventType.DECISION, EventType.NOTE}


def test_correction_perime_la_decision_du_meme_fil(tmp_path):
    jp = tmp_path / "journal.jsonl"
    log(jp, "decision", "Licence MIT pour le projet", session_id="licence", now=T0)
    log(jp, "correction", "En fait Apache-2.0 (octroi de brevet)", session_id="licence",
        now=T0 + timedelta(hours=1))
    hit = [h for h in recall(read_events(jp), "licence projet") if h["type"] == "decision"][0]
    assert hit["superseded"] is True                  # C3 : decision anterieure perimee
    assert len(hit["corrected_by"]) == 1


def test_texte_vide_rejete():
    import pytest
    with pytest.raises(ValueError):
        make_event("decision", "   ", now=T0)


def test_source_project_isole_du_chat(tmp_path):
    """Source dediee 'project:' -> recall(source_prefix='project') ignore le chat eve."""
    from multiservice.events import AetherEvent
    jp = tmp_path / "journal.jsonl"
    log(jp, "decision", "Licence Apache-2.0 pour le projet", session_id="licence", now=T0)  # source project:wilfred
    # un event facon chat eve (source user:wilfred) qui parle aussi de licence/Apache
    eve = AetherEvent(type=EventType.PROMPT, title="prompt", description="config Apache reverse proxy",
                      source="user:wilfred", observed_at=T0,
                      data={"text": "config Apache reverse proxy", "session_id": "eve", "turn_id": "t"})
    from multiservice.journal import append_events
    append_events(jp, [eve])
    evs = read_events(jp)
    only_project = recall(evs, "licence Apache projet", source_prefix="project")
    assert only_project and all(h["source"].startswith("project") for h in only_project)
    assert not any("reverse proxy" in h["text"] for h in only_project)   # bruit eve ecarte
