"""Revue LLM de curation (CLI, lecture seule) : ecrit un .md date, ne mute PAS le journal.
Backend injecte (FakeBackend a verdict canned) : ni reseau, ni modele."""
import json
from datetime import datetime, timezone, timedelta

from multiservice import curation_llm as cl
from multiservice.backends import Completion
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ev(text, vf, typ=EventType.NOTE, sid="s"):
    return AetherEvent(type=typ, title=typ.value, description=text, source="project:maison",
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


class FakeBackend:
    model_id = "qwen-local"

    def __init__(self, text):
        self._t = text

    def chat(self, messages, on_token=None, tools=None):
        return Completion(self._t, self.model_id, 1, 1)


def _v(rel, keep=None):
    d = {"relation": rel, "rationale": "r"}
    if keep:
        d["keep"] = keep
    return json.dumps(d)


def test_run_ecrit_revue_llm_datee_et_ne_mute_pas(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [
        _ev("reindex incremental garde index frais sans etape manuelle tache", T0),
        _ev("reindex incremental garde index frais sans etape manuelle tache horaire", T0 + timedelta(hours=1)),
    ])
    before = [e.id for e in read_events(str(jp))]
    path, needs, result = cl.run(str(jp), str(tmp_path / "out"),
                                 backend=FakeBackend(_v("equivalent", "a")), now=NOW)
    assert needs is True and len(result["consolidations"]) == 1
    md = (tmp_path / "out" / "curation-llm-20260706.md").read_text(encoding="utf-8")
    assert "--closes" in md
    assert path.endswith("curation-llm-20260706.md")
    assert [e.id for e in read_events(str(jp))] == before     # LECTURE SEULE


def test_run_rien_a_proposer(tmp_path):
    jp = tmp_path / "j.jsonl"
    append_events(str(jp), [_ev("adopter apache-2.0 pour la licence", T0)])   # 1 fait -> aucun candidat
    _, needs, result = cl.run(str(jp), str(tmp_path / "out"),
                              backend=FakeBackend(_v("different")), now=NOW)
    assert needs is False and result["consolidations"] == []
