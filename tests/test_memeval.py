"""Harnais d'évaluation de la mémoire (Phase 1, PUR, sans modèle). « Mesuré, pas promis. »
Vérité-terrain auto-construite depuis le journal : chaque correction C3 vise les faits qu'elle
corrige -> jeu doré. Métriques precision@k / recall@k / hit_rate. Fonction de recall injectée."""
from datetime import datetime, timezone, timedelta

from multiservice.events import AetherEvent, EventType
from multiservice.memeval import hits_at_k, evaluate, golden_from_corrections

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid="s"):
    return AetherEvent(type=typ, title=typ.value, description=text, source="project:demo",
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def test_hits_at_k_compte_precision_et_recall():
    m = hits_at_k(["a", "b"], ["a", "x", "b", "y"], k=3)   # top-3 = a, x, b
    assert m["hits"] == 2 and m["recall"] == 1.0 and m["precision"] == round(2 / 3, 3)


def test_hits_at_k_aucun():
    m = hits_at_k(["a"], ["x", "y", "z"], k=3)
    assert m["hits"] == 0 and m["recall"] == 0.0 and m["precision"] == 0.0


def test_evaluate_agrege_les_requetes():
    golden = [{"query": "q1", "relevant_ids": ["a"]}, {"query": "q2", "relevant_ids": ["b"]}]
    retrieved = {"q1": ["a", "z"], "q2": ["z", "w"]}       # q1 touche, q2 manque
    r = evaluate(golden, lambda q: retrieved[q], k=2)
    assert r["n_queries"] == 2 and r["hit_rate"] == 0.5
    assert r["mean_recall"] == 0.5


def test_golden_from_corrections_utilise_la_structure_c3():
    evs = [_ev(EventType.DECISION, "moteur NEMA-17", T0, "arm"),
           _ev(EventType.CORRECTION, "en fait servo MG996R", T0 + timedelta(days=1), "arm"),
           _ev(EventType.DECISION, "hors sujet", T0, "autre")]
    g = golden_from_corrections(evs)
    assert len(g) == 1
    assert g[0]["query"] == "en fait servo MG996R"
    assert evs[0].id in g[0]["relevant_ids"]               # la decision de la meme session
    assert evs[2].id not in g[0]["relevant_ids"]           # autre session -> exclu


def test_golden_vide_si_aucune_correction():
    assert golden_from_corrections([_ev(EventType.DECISION, "seule", T0, "s")]) == []


def test_compare_plusieurs_methodes():
    from multiservice.memeval import compare
    golden = [{"query": "q", "relevant_ids": ["a"]}]
    r = compare(golden, {"lexical": lambda q: ["z"], "semantic": lambda q: ["a"]}, k=1)
    assert r["lexical"]["hit_rate"] == 0.0 and r["semantic"]["hit_rate"] == 1.0
