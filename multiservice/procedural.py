"""Mémoire procédurale — le 3e étage cognitif (épisodique -> sémantique -> PROCÉDURAL).

Frère procédural de `skills.py` (S17), même discipline (D10/BITS) : on OBSERVE les séquences
d'outils qui RÉUSSISSENT et RECURRENT, on les cristallise en **playbooks candidats** (suggestion
seule, promotion humaine). La mémoire cesse de rappeler des faits, elle transmet des **méthodes** —
de l'apprentissage sans toucher aux poids.

Phase 1 = DÉTECTION, LECTURE SEULE, PURE : `List[AetherEvent] -> candidats`. Ne mute rien (test
structurel). Un « tour réussi » = un `turn_id` dont TOUS les `tool_result` sont `ok` et qui enchaîne
>= `min_len` outils. La séquence ORDONNÉE des noms d'outils est la signature du playbook.

Suites (hors Phase 1) : distillation LLM local d'un playbook lisible, validation via l'inbox de
curation (C1), injection à la reprise via `forecast`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .events import AetherEvent, EventType
from .skills import _confidence                       # même courbe 1 - 0.5^n (cohérence S17)


def _turns(events: List[AetherEvent]) -> Dict[Any, Dict[str, Any]]:
    """Regroupe par `turn_id` : {seq: [noms d'outils, dans l'ordre], oks: [bool], session}. PUR."""
    turns: Dict[Any, Dict[str, Any]] = {}
    for e in events:
        tid = e.data.get("turn_id")
        if tid is None:
            continue
        t = turns.setdefault(tid, {"seq": [], "oks": [], "session": e.data.get("session_id")})
        if e.type == EventType.TOOL_CALL:
            t["seq"].append(e.data.get("tool") or e.description)
        elif e.type == EventType.TOOL_RESULT:
            t["oks"].append(bool(e.data.get("ok", False)))
    return turns


def _turn_prompts(events: List[AetherEvent]) -> Dict[Any, str]:
    """{turn_id: texte du prompt} — pour donner un ÉCHANTILLON de contexte au playbook. PUR."""
    out: Dict[Any, str] = {}
    for e in events:
        if e.type == EventType.PROMPT:
            tid = e.data.get("turn_id")
            if tid is not None and tid not in out:
                out[tid] = e.data.get("text", "") or e.description or ""
    return out


def _successful(events: List[AetherEvent], min_len: int) -> List[Tuple[Any, Tuple[str, ...]]]:
    """(turn_id, séquence) des tours RÉUSSIS (>= min_len outils, tous les résultats ok). PUR."""
    out = []
    for tid, t in _turns(events).items():
        seq = t["seq"]
        if len(seq) >= min_len and t["oks"] and all(t["oks"]):
            out.append((tid, tuple(seq)))
    return out


def playbook_candidates(events: List[AetherEvent], min_occurrences: int = 2,
                        min_len: int = 2) -> List[Dict[str, Any]]:
    """Séquences d'outils réussies et RÉCURRENTES (>= min_occurrences) -> playbooks candidats
    (type=playbook_suggestion). PUR, LECTURE SEULE. L'ordre distingue les playbooks. Promotion HUMAINE."""
    prompts = _turn_prompts(events)
    tid_session = {tid: t["session"] for tid, t in _turns(events).items()}
    groups: Dict[Tuple[str, ...], List[Any]] = {}
    for tid, sig in _successful(events, min_len):
        groups.setdefault(sig, []).append(tid)
    cands = []
    for sig, tids in groups.items():
        n = len(tids)
        if n >= min_occurrences:
            cands.append({
                "type": "playbook_suggestion",
                "tools": list(sig),
                "signature": " -> ".join(sig),
                "count": n,
                "confidence": _confidence(n),
                "evidence": tids[:8],
                "sample_prompt": next((prompts.get(t, "") for t in tids if prompts.get(t)), ""),
                "sessions": sorted({tid_session.get(t) for t in tids if tid_session.get(t) is not None}),
            })
    return sorted(cands, key=lambda c: (-c["count"], c["signature"]))


def suggest_for_session(events: List[AetherEvent], session_id: Any,
                        min_occurrences: int = 2) -> Optional[Dict[str, Any]]:
    """Le playbook RÉCURRENT DOMINANT observé dans cette session (« ta méthode ici »), ou None.
    PUR, LECTURE SEULE, **aucun appel modèle** — pour l'injection à la reprise (via `forecast`)."""
    here = [c for c in playbook_candidates(events, min_occurrences=min_occurrences)
            if session_id in c.get("sessions", [])]
    if not here:
        return None
    top = max(here, key=lambda c: (c["count"], c["confidence"]))
    return {"tools": top["tools"], "signature": top["signature"],
            "count": top["count"], "confidence": top["confidence"]}


_SYSTEM_PLAYBOOK = (
    "Tu transformes une SEQUENCE d'outils reussie et recurrente en PLAYBOOK reutilisable. "
    "Reponds STRICTEMENT en JSON sur une ligne : "
    "{\"title\": \"...\", \"when_to_use\": \"...\", \"steps\": [\"...\"]}. "
    "steps = une phrase actionnable par outil, dans l'ordre. Tu decris une METHODE observee, "
    "tu n'inventes aucun fait."
)


def distill_playbook(backend, candidate: Dict[str, Any], retries: int = 2) -> Dict[str, Any]:
    """Distille une séquence d'outils (candidate) en playbook LISIBLE via un LLM LOCAL. Le LLM
    PROPOSE (l'humain valide) ; il décrit une méthode observée, n'écrit rien. Robuste : erreur /
    JSON illisible -> `status=uncertain` (jamais de playbook à l'aveugle). PUR vis-à-vis du backend."""
    from .comparator import _parse
    tools = list(candidate.get("tools", []))
    user = (f"Sequence d'outils (dans l'ordre) : {' -> '.join(tools)}\n"
            f"Exemple de contexte : {(candidate.get('sample_prompt') or '')[:300]}\n"
            "Ta reponse JSON :")
    msgs = [{"role": "system", "content": _SYSTEM_PLAYBOOK}, {"role": "user", "content": user}]
    for _ in range(retries + 1):
        try:
            c = backend.chat(msgs)
            d = _parse(getattr(c, "text", "") or "")
        except Exception:
            continue
        if not d or not isinstance(d.get("steps"), list) or not d["steps"]:
            return {"status": "uncertain", "tools": tools}
        return {"status": "proposed",
                "title": str(d.get("title", ""))[:120],
                "when_to_use": str(d.get("when_to_use", ""))[:200],
                "steps": [str(s)[:160] for s in d["steps"]][:12],
                "tools": tools}
    return {"status": "uncertain", "tools": tools}


def format_candidates(cands: List[Dict[str, Any]]) -> str:
    if not cands:
        return "Aucun playbook candidat (aucune séquence d'outils réussie vue >= 2 fois)."
    L = ["Playbooks candidats (SUGGESTION seule - promotion humaine, C1) :", "-" * 64]
    for c in cands:
        L.append(f"  {c['signature']}   (réussi {c['count']}x, confiance={c['confidence']})")
    L.append("-" * 64)
    L.append("La mémoire transmet une MÉTHODE, pas un fait. À valider (inbox) avant promotion.")
    return "\n".join(L)


def main() -> None:
    import argparse

    from . import config
    from .journal import read_events
    p = argparse.ArgumentParser(description="Mémoire procédurale (détection de playbooks, lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--min", type=int, default=2, dest="min_occurrences",
                   help="récurrence minimale avant de suggérer (défaut 2)")
    p.add_argument("--min-len", type=int, default=2, dest="min_len",
                   help="longueur minimale d'une procédure (défaut 2 outils)")
    a = p.parse_args()
    print(format_candidates(playbook_candidates(read_events(a.journal),
                                                a.min_occurrences, a.min_len)))


if __name__ == "__main__":
    main()
