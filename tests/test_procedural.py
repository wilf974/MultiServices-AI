"""Mémoire procédurale (Phase 1, DETECTION, lecture seule) : le 3e étage cognitif.
Frère procédural de skills.py : cristallise les SÉQUENCES D'OUTILS récurrentes des tours RÉUSSIS
(tous les tool_result ok) -> playbooks candidats (suggestion ; promotion humaine). PUR, ne mute rien.
"""
import copy
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.procedural import playbook_candidates

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _turn(tid, tools, oks=None, sid="s"):
    oks = oks if oks is not None else [True] * len(tools)
    evs = []
    for tool, ok in zip(tools, oks):
        evs.append(AetherEvent(type=EventType.TOOL_CALL, title="tool_call", description=tool,
                               source="llm:m", observed_at=T0,
                               data={"session_id": sid, "turn_id": tid, "tool": tool, "arguments": {}}))
        evs.append(AetherEvent(type=EventType.TOOL_RESULT, title="tool_result", description=tool,
                               source="memory", observed_at=T0,
                               data={"session_id": sid, "turn_id": tid, "tool": tool, "ok": ok,
                                     "result_preview": ""}))
    return evs


def test_sequence_reussie_recurrente_suggeree():
    evs = _turn("t1", ["recall", "remember"]) + _turn("t2", ["recall", "remember"])
    c = playbook_candidates(evs, min_occurrences=2)
    assert len(c) == 1
    assert c[0]["tools"] == ["recall", "remember"] and c[0]["count"] == 2
    assert c[0]["confidence"] == 0.75                      # 1 - 0.5^2


def test_ordre_compte_deux_procedures_distinctes():
    evs = (_turn("t1", ["recall", "remember"]) + _turn("t2", ["recall", "remember"])
           + _turn("t3", ["remember", "recall"]) + _turn("t4", ["remember", "recall"]))
    c = playbook_candidates(evs, min_occurrences=2)
    assert len(c) == 2                                      # l'ordre distingue le playbook


def test_tour_echoue_non_compte():
    evs = _turn("t1", ["recall", "remember"], oks=[True, False]) + _turn("t2", ["recall", "remember"])
    assert playbook_candidates(evs, min_occurrences=2) == []   # 1 seul reussi -> sous le seuil


def test_procedure_d_un_seul_outil_ignoree():
    evs = _turn("t1", ["recall"]) + _turn("t2", ["recall"])
    assert playbook_candidates(evs, min_occurrences=2) == []   # 1 outil != procedure (min_len=2)


def test_vue_unique_sous_le_seuil():
    assert playbook_candidates(_turn("t1", ["a", "b", "c"]), min_occurrences=2) == []


def test_lecture_seule_pure():
    evs = _turn("t1", ["recall", "remember"]) + _turn("t2", ["recall", "remember"])
    snap = copy.deepcopy([e.model_dump() for e in evs])
    playbook_candidates(evs)
    assert [e.model_dump() for e in evs] == snap
