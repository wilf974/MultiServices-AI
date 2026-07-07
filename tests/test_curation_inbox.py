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


# --- fermeture de la boucle : les playbooks aussi passent par l'inbox ---

def _tool_turn(tid, tools):
    evs = []
    for tool in tools:
        evs.append(AetherEvent(type=EventType.TOOL_CALL, title="tc", description=tool, source="llm:m",
                               observed_at=T0, data={"session_id": "sx", "turn_id": tid, "tool": tool,
                                                     "arguments": {}}))
        evs.append(AetherEvent(type=EventType.TOOL_RESULT, title="tr", description=tool, source="memory",
                               observed_at=T0, data={"session_id": "sx", "turn_id": tid, "tool": tool,
                                                     "ok": True}))
    return evs


def _tool_journal():
    return _tool_turn("t1", ["recall", "remember"]) + _tool_turn("t2", ["recall", "remember"])


def test_pending_inclut_les_playbooks():
    pb = [p for p in inbox.pending(_tool_journal()) if p["action"] == "promote_playbook"]
    assert len(pb) == 1 and pb[0]["tools"] == ["recall", "remember"]


def test_approuver_un_playbook_le_promeut():
    pb = [p for p in inbox.pending(_tool_journal()) if p["action"] == "promote_playbook"][0]
    payload = inbox.apply_decision(pb, "approve")
    assert payload["session"] == "playbooks"
    assert payload["data"]["playbook"]["tools"] == ["recall", "remember"]


def test_rejeter_un_playbook_ne_revient_plus():
    pb = [p for p in inbox.pending(_tool_journal()) if p["action"] == "promote_playbook"][0]
    payload = inbox.apply_decision(pb, "reject")
    assert payload["data"]["reject_playbook"] == pb["signature"]
