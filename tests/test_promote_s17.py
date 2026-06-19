"""S17 (fin) - promotion human-gated : SKILL.md, versionnage C3, retire, sante (D11)."""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.journal import read_events
from multiservice.promote import (build_skill_md, current_version, promote, retire,
                                   skill_health)

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def test_build_skill_md_pur():
    md = build_skill_md("hfsql", "Connecteur HFSQL/ODBC", "corps", trigger="odbc+hfsql",
                        evidence=["e1", "e2"], version=1, created=T0)
    assert md.startswith("---")
    assert "name: hfsql" in md and "version: 1" in md and "trigger: odbc+hfsql" in md
    assert md.rstrip().endswith("corps")


def test_promote_ecrit_skill_md_et_journalise(tmp_path):
    jp = tmp_path / "journal.jsonl"; sd = tmp_path / "skills"
    ev = promote("hfsql", "Connecteur", "doc v1", sd, jp, trigger="odbc+hfsql",
                 evidence=["e1"], now=T0)
    assert (sd / "hfsql" / "SKILL.md").exists()
    assert ev.type == EventType.DECISION and ev.source == "user:wilfred"
    assert ev.data["action"] == "promote_skill" and ev.data["version"] == 1
    # journalise (append-only)
    evs = read_events(jp)
    assert any(e.data.get("action") == "promote_skill" for e in evs)


def test_versionnage_archive_sans_perte(tmp_path):
    jp = tmp_path / "journal.jsonl"; sd = tmp_path / "skills"
    promote("hfsql", "Connecteur", "doc v1", sd, jp, trigger="odbc", now=T0)
    ev2 = promote("hfsql", "Connecteur", "doc v2", sd, jp, trigger="odbc",
                  now=T0 + timedelta(days=1))
    assert ev2.data["version"] == 2
    assert "supersedes" in ev2.data                      # lignee bi-temporelle
    assert (sd / "hfsql" / "SKILL.v1.md").exists()        # ancienne archivee (C3, rien perdu)
    assert "doc v2" in (sd / "hfsql" / "SKILL.md").read_text(encoding="utf-8")
    assert current_version("hfsql", read_events(jp)) == 2


def test_retire_cloture_sans_effacer(tmp_path):
    jp = tmp_path / "journal.jsonl"; sd = tmp_path / "skills"
    promote("hfsql", "Connecteur", "doc", sd, jp, trigger="odbc", now=T0)
    ev = retire("hfsql", jp, "obsolete", now=T0 + timedelta(days=2))
    assert ev.data["action"] == "retire_skill" and "closes" in ev.data
    assert (sd / "hfsql" / "SKILL.md").exists()            # fichier conserve (jamais supprime)


def _user_prompt(text, at):
    return AetherEvent(type=EventType.PROMPT, title="p", description=text,
                       source="user:wilfred", observed_at=at, data={"text": text})


def test_sante_fenetre_muette_signal_a():
    # declencheur 'odbc hfsql' vu recemment -> pas peremptee
    recent = [_user_prompt("connecteur odbc hfsql", T0)]
    h = skill_health("hfsql", "odbc+hfsql", recent, now=T0 + timedelta(days=3))
    assert h["stale_trigger"] is False
    # vu il y a longtemps -> peremptee (fenetre muette)
    h2 = skill_health("hfsql", "odbc+hfsql", recent, now=T0 + timedelta(days=30))
    assert h2["stale_trigger"] is True
    # jamais vu -> peremptee
    h3 = skill_health("hfsql", "odbc+hfsql", [], now=T0)
    assert h3["stale_trigger"] is True
