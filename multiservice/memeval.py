"""Harnais d'évaluation de la mémoire — « mesuré, pas promis ».

Phase 1 : PUR, sans modèle. Vérité-terrain AUTO-CONSTRUITE depuis le journal (dogfooding) : chaque
correction C3 vise les faits qu'elle corrige (les faits antérieurs de sa session) -> un jeu doré
{query, relevant_ids}. On mesure si une fonction de recall (injectée) retrouve ces faits :
`precision@k`, `recall@k`, `hit_rate`. Aucune écriture, aucun appel modèle.

Phase 2 (hors ici, nécessite un modèle) : A/B « réponse avec vs sans mémoire » jugée localement,
taux de faux-servis du cache sémantique.

Lancer : `python -m multiservice.memeval` (évalue `memory.recall` sur le journal réel).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from .events import AetherEvent, EventType

# Faits « rédigés » qu'une correction peut viser (jamais les tours bruts de chat).
_FACT_TYPES = {EventType.DECISION, EventType.NOTE, EventType.OBSERVATION,
               EventType.VALIDATION, EventType.HYPOTHESIS}


def hits_at_k(relevant_ids, retrieved_ids, k: int = 5) -> Dict[str, Any]:
    """precision@k / recall@k / nb de hits pour UNE requête. PUR."""
    rel = set(relevant_ids)
    topk = list(retrieved_ids)[:k]
    n = sum(1 for r in topk if r in rel)
    return {"hits": n,
            "precision": round(n / len(topk), 3) if topk else 0.0,
            "recall": round(n / len(rel), 3) if rel else 0.0,
            "relevant": len(rel)}


def evaluate(golden: List[Dict[str, Any]], retrieve_fn: Callable[[str], List[str]],
             k: int = 5) -> Dict[str, Any]:
    """Évalue `retrieve_fn` (query -> liste d'ids ordonnée) sur un jeu doré. PUR. `retrieve_fn` est
    INJECTÉE : fake en test, `memory.recall` en prod. Agrège precision/recall/hit_rate."""
    per = []
    for g in golden:
        m = hits_at_k(g["relevant_ids"], retrieve_fn(g["query"]), k)
        per.append({"query": g["query"][:80], **m})
    n = len(per) or 1
    return {
        "k": k,
        "n_queries": len(per),
        "mean_precision": round(sum(p["precision"] for p in per) / n, 3),
        "mean_recall": round(sum(p["recall"] for p in per) / n, 3),
        "hit_rate": round(sum(1 for p in per if p["hits"] > 0) / n, 3),
        "per_query": per,
    }


def golden_from_corrections(events: List[AetherEvent]) -> List[Dict[str, Any]]:
    """Jeu doré auto-construit : {query=texte de la correction, relevant_ids=faits antérieurs de SA
    session}. PUR. C'est la structure bi-temporelle du journal qui sert de vérité-terrain."""
    floor = datetime.min.replace(tzinfo=timezone.utc)

    def _vf(e):
        vf = e.valid_from
        if vf is not None and vf.tzinfo is None:
            vf = vf.replace(tzinfo=timezone.utc)
        return vf or floor

    golden = []
    for c in events:
        if c.type != EventType.CORRECTION:
            continue
        sid = c.data.get("session_id")
        if sid is None:
            continue
        cvf = _vf(c)
        relevant = [e.id for e in events
                    if e.type in _FACT_TYPES and e.data.get("session_id") == sid and _vf(e) < cvf]
        if relevant:
            golden.append({"query": (c.data.get("text") or c.description or ""),
                           "relevant_ids": relevant})
    return golden


def main() -> None:
    import argparse

    from . import config, memory
    from .journal import read_events
    p = argparse.ArgumentParser(description="Harnais d'évaluation de la mémoire (Phase 1, lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--k", type=int, default=5)
    a = p.parse_args()
    events = read_events(a.journal)
    golden = golden_from_corrections(events)
    if not golden:
        print("[memeval] aucun jeu dore (aucune correction avec des faits anterieurs).")
        return

    def retrieve(q: str) -> List[str]:
        return [h.get("id") for h in memory.recall(events, q, k=a.k)]

    r = evaluate(golden, retrieve, a.k)
    print(f"[memeval] recall lexical @k={r['k']} sur {r['n_queries']} corrections (jeu dore) : "
          f"hit_rate={r['hit_rate']}  mean_recall={r['mean_recall']}  mean_precision={r['mean_precision']}")


if __name__ == "__main__":
    main()
