"""Synchro multi-machines — coeur : merge_journal (append-only, dedup par id, idempotent).

Contrat : ajoute uniquement les events absents (par id) ; re-fusionner n'ajoute rien ; jamais de
reecriture ni de suppression des events deja presents.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.events import EventType
from multiservice.journal import append_events, read_events
from multiservice.projlog import make_event
from multiservice.sync import merge_journal

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _seed(path, texts, src="project:a"):
    evs = [make_event("decision", t, source=src, session_id="s", now=T0) for t in texts]
    append_events(path, evs)
    return evs


def test_fusionne_uniquement_le_neuf(tmp_path):
    host = tmp_path / "host.jsonl"
    remote = tmp_path / "remote.jsonl"
    _seed(host, ["decision hote A"])
    _seed(remote, ["decision distante B", "decision distante C"])
    r = merge_journal(host, remote)
    assert r["added"] == 2 and r["source_total"] == 2
    assert len(read_events(host)) == 3                  # A + B + C


def test_idempotent(tmp_path):
    host = tmp_path / "host.jsonl"
    remote = tmp_path / "remote.jsonl"
    _seed(remote, ["x", "y"])
    merge_journal(host, remote)
    r2 = merge_journal(host, remote)                    # 2e fois : rien de neuf
    assert r2["added"] == 0
    assert len(read_events(host)) == 2


def test_ne_reecrit_pas_l_existant(tmp_path):
    host = tmp_path / "host.jsonl"
    remote = tmp_path / "remote.jsonl"
    shared = _seed(host, ["partagee"])                  # meme event des deux cotes
    append_events(remote, shared)
    _seed(remote, ["nouvelle distante"])                # + un neuf
    before = host.read_text(encoding="utf-8")
    r = merge_journal(host, remote)
    assert r["added"] == 1                              # seul le neuf
    assert host.read_text(encoding="utf-8").startswith(before)   # l'existant intact, juste appende


def test_source_absente_est_sure(tmp_path):
    host = tmp_path / "host.jsonl"
    _seed(host, ["a"])
    r = merge_journal(host, tmp_path / "nexiste-pas.jsonl")
    assert r["added"] == 0 and r["source_total"] == 0
