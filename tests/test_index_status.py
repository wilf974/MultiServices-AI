"""Amelioration MCP #4 — signal de fraicheur d'index (recall_semantic).

Contrat : index_coverage dit combien d'evenements INDEXABLES (texte, valides a as_of) sont
couverts par l'index d'embeddings, et si l'index est FRAIS. PUR, lecture seule.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import index_coverage

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)


def _ev(text, at=T0, vt=None):
    return AetherEvent(type=EventType.COMPLETION, title="x", description=text, source="llm:eve",
                       observed_at=at, valid_to=vt, data={"text": text, "turn_id": "t", "session_id": "s"})


def test_couverture_partielle_n_est_pas_fraiche():
    e1, e2, e3 = _ev("aaa"), _ev("bbb"), _ev("ccc")
    vecs = {e1.id: [1.0], e2.id: [1.0]}            # 2 indexes sur 3
    cov = index_coverage([e1, e2, e3], vecs)
    assert cov["eligible"] == 3 and cov["indexed"] == 2 and cov["missing"] == 1
    assert cov["fresh"] is False and cov["covered_pct"] == 66.7


def test_tout_indexe_est_frais():
    e1, e2 = _ev("aaa"), _ev("bbb")
    cov = index_coverage([e1, e2], {e1.id: [1.0], e2.id: [1.0]})
    assert cov["fresh"] is True and cov["covered_pct"] == 100.0


def test_evenement_futur_non_eligible():
    e1 = _ev("present", at=T0)
    e2 = _ev("futur", at=T0 + timedelta(days=2))
    cov = index_coverage([e1, e2], {e1.id: [1.0]}, as_of=T0)
    assert cov["eligible"] == 1 and cov["fresh"] is True   # le futur ne compte pas a as_of


def test_sans_texte_non_indexable():
    e = AetherEvent(type=EventType.TOKEN_USAGE, title="tok", source="meter", observed_at=T0,
                    data={"turn_id": "t", "session_id": "s"})   # pas de 'text'
    cov = index_coverage([e], {})
    assert cov["eligible"] == 0 and cov["fresh"] is True


def test_journal_vide_est_frais():
    assert index_coverage([], {})["fresh"] is True


def test_decision_et_raisonnement_indexables():
    """Decisions/hypotheses/... sont desormais indexables -> retrouvables PAR LE SENS."""
    for typ in (EventType.DECISION, EventType.NOTE, EventType.HYPOTHESIS,
                EventType.OBSERVATION, EventType.VALIDATION):
        e = AetherEvent(type=typ, title="x", description="Licence Apache-2.0",
                        source="project:wilfred", observed_at=T0,
                        data={"text": "Licence Apache-2.0", "session_id": "s", "turn_id": "t"})
        cov = index_coverage([e], {})
        assert cov["eligible"] == 1, typ
