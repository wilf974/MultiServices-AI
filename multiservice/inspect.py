"""Observabilite d'usage LLM (lecture seule) - premiere brique S15.

Lit le journal LLM et RAPPORTE : tours, tokens in/out par tour et cumules, par
(model_id, count_source), et un proxy honnete de re-envoi de prefixe par session.
NE MUTE RIEN, ne calibre aucun seuil (on observe, cf. discipline BITS).

Sorties console en ASCII (convention AetherCore).

Usage : python -m multiservice.inspect            (journal par defaut)
        python -m multiservice.inspect --journal <chemin>
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List

from . import config
from .events import AetherEvent, EventType
from .journal import read_events


def summarize(events: List[AetherEvent]) -> Dict[str, Any]:
    """Agrege les evenements en stats d'usage. PUR (entree -> dict)."""
    turns: Dict[str, Dict[str, Any]] = {}
    first_seen: Dict[str, Any] = {}
    for e in events:
        tid = e.data.get("turn_id")
        if tid is None:
            continue
        t = turns.setdefault(tid, {"session_id": e.data.get("session_id"),
                                   "in": 0, "out": 0, "saved": 0, "measured": False,
                                   "model_id": None, "count_source": None})
        if tid not in first_seen or e.valid_from < first_seen[tid]:
            first_seen[tid] = e.valid_from
        if e.type == EventType.PROMPT:
            t["prompt"] = e.data.get("text", "")
        elif e.type == EventType.COMPLETION:
            t["model_id"] = e.data.get("model_id", t["model_id"])
        elif e.type == EventType.TOKEN_USAGE:
            t["in"] = int(e.data.get("input_tokens", 0))
            t["out"] = int(e.data.get("output_tokens", 0))
            t["count_source"] = e.data.get("count_source")
            t["model_id"] = e.data.get("model_id", t["model_id"])
            t["saved"] = int(e.data.get("saved_input_tokens", 0))
            if "full_input_tokens" in e.data:
                t["measured"] = True

    ordered = [turns[tid] for tid in sorted(turns, key=lambda k: first_seen[k])]

    by_basis: Dict[Any, Dict[str, int]] = {}
    for t in ordered:
        key = (t["model_id"], t["count_source"])
        b = by_basis.setdefault(key, {"turns": 0, "in": 0, "out": 0, "saved": 0})
        b["turns"] += 1; b["in"] += t["in"]; b["out"] += t["out"]; b["saved"] += t.get("saved", 0)

    sessions: Dict[Any, Dict[str, Any]] = {}
    for t in ordered:
        sid = t["session_id"]
        s = sessions.setdefault(sid, {"session_id": sid, "inputs": [], "in": 0, "out": 0, "saved": 0, "measured": False})
        s["inputs"].append(t["in"]); s["in"] += t["in"]; s["out"] += t["out"]; s["saved"] += t.get("saved", 0)
        s["measured"] = s["measured"] or t.get("measured", False)
    for s in sessions.values():
        # proxy honnete : tokens d'entree re-envoyes = somme(in) - plus gros tour.
        # = ce qu'un cache de prefixe PARFAIT economiserait (chat lineaire). Estimation.
        s["redundant_prefix"] = max(0, s["in"] - (max(s["inputs"]) if s["inputs"] else 0))

    totals = {"turns": len(ordered),
              "in": sum(t["in"] for t in ordered),
              "out": sum(t["out"] for t in ordered),
              "saved": sum(t.get("saved", 0) for t in ordered)}
    totals["total"] = totals["in"] + totals["out"]
    return {"n_events": len(events), "turns": ordered, "by_basis": by_basis,
            "sessions": list(sessions.values()), "totals": totals}


def format_report(s: Dict[str, Any]) -> str:
    L = []
    tot = s["totals"]
    L.append(f"MultiService AI - usage (lecture seule)  evenements={s['n_events']} tours={tot['turns']}")
    L.append("-" * 64)
    L.append("Par base de comptage (model_id, count_source) - jamais somme entre bases:")
    for (mid, cs), b in sorted(s["by_basis"].items(), key=lambda kv: str(kv[0])):
        L.append(f"  {str(mid):28} [{cs}]  tours={b['turns']:3}  in={b['in']:7}  out={b['out']:7}")
    L.append("-" * 64)
    L.append("Par session (boule de neige du contexte):")
    for ses in s["sessions"]:
        traj = "->".join(str(x) for x in ses["inputs"])
        red = ses["redundant_prefix"]
        pct = (100 * red / ses["in"]) if ses["in"] else 0
        L.append(f"  session {str(ses['session_id'])[:8]}  in_traj=[{traj}]")
        L.append(f"    in={ses['in']} out={ses['out']}  re-envoi prefixe (proxy)={red} ({pct:.0f}% de l'entree)")
    L.append("-" * 64)
    L.append(f"CUMUL  in={tot['in']}  out={tot['out']}  total={tot['total']}")
    L.append("(proxy re-envoi = somme(in) - plus gros tour par session ; estimation, chat lineaire)")
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser(description="Observabilite d'usage LLM (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    args = p.parse_args()
    print(format_report(summarize(read_events(args.journal))))


if __name__ == "__main__":
    main()
