"""Inbox de curation : liste les propositions en attente (enrichies des textes) et transforme
une decision humaine (approuver/rejeter) en payload d'ecriture. Coeur PUR, testable.
Approuver = cloture C3 (data.closes) ; rejeter = data.rejects (ne revient plus)."""
from datetime import datetime, timezone, timedelta

from multiservice import curation_inbox as inbox
from multiservice.curator import CLOSURE_SESSION
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ev(text, vf, sid="s"):
    return AetherEvent(type=EventType.NOTE, title="n", description=text, source="project:demo",
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def _dup_journal():
    # deux notes au texte identique -> 1 proposition close_duplicate
    return [_ev("meme fait exact", T0), _ev("meme fait exact", T0 + timedelta(hours=1))]


def test_pending_enrichit_les_textes_et_la_commande():
    p = inbox.pending(_dup_journal())
    assert len(p) == 1
    prop = p[0]
    assert prop["keep_text"] == "meme fait exact"
    assert prop["close_texts"] == ["meme fait exact"]
    assert prop["keep_id"] and prop["close_ids"] and prop["keep_id"] not in prop["close_ids"]
    assert "--closes" in prop["command"]


def test_apply_approve_produit_une_cloture_c3():
    prop = inbox.pending(_dup_journal())[0]
    payload = inbox.apply_decision(prop, "approve")
    assert payload["kind"] == "correction"
    assert payload["session"] == CLOSURE_SESSION
    assert payload["data"]["closes"] == prop["close_ids"]
    assert prop["keep_id"] not in payload["data"]["closes"]      # l'original survit


def test_apply_reject_produit_des_rejets():
    prop = inbox.pending(_dup_journal())[0]
    payload = inbox.apply_decision(prop, "reject")
    assert payload["kind"] == "note"
    assert payload["data"]["rejects"] == prop["close_ids"]
    assert "closes" not in payload["data"]


def test_apply_decision_inconnue_leve():
    prop = inbox.pending(_dup_journal())[0]
    try:
        inbox.apply_decision(prop, "n_importe_quoi")
        assert False, "aurait du lever"
    except ValueError:
        pass


def test_journal_propre_aucune_proposition():
    assert inbox.pending([_ev("un seul fait", T0)]) == []
