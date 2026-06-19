"""Sprint 15 - economy : MESURER (lecture seule). On ne coupe rien, on ne cache rien.

Construit sur inspect.summarize. Deux sorties :
  usage_digest(summary)      -> bloc 'Usage:' (totaux par modele, top sessions, % redondant)
  detect_redundancy(summary) -> sessions au-dessus d'un seuil de re-envoi de prefixe.

SEUILS CALIBRES SUR LE REEL (journal du 16 juin 2026, 169 tours) :
  - une session a 52/70/99% de re-envoi merite un signalement ;
  - le bruit (sessions courtes a 0-10%) ne doit PAS etre flagge.
  D'ou : pct_threshold=0.50 et min_input=1000 (plancher anti-bruit). Ajustables.
  (Discipline BITS : seuils observes, pas inventes. report only - aucune action.)

Sorties console ASCII.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List

from . import config
from .inspect import summarize
from .journal import read_events

PCT_THRESHOLD = 0.50   # part de l'entree qui est du re-envoi de prefixe
MIN_INPUT = 1000       # plancher : en-dessous, une session est trop petite pour compter


def usage_digest(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Bloc Usage condense. PUR."""
    sessions = summary["sessions"]
    total_in = summary["totals"]["in"]
    total_red = sum(s["redundant_prefix"] for s in sessions)
    top = sorted(sessions, key=lambda s: s["redundant_prefix"], reverse=True)[:5]
    saved = summary["totals"].get("saved", 0)
    return {
        "by_basis": summary["by_basis"],
        "totals": summary["totals"],
        "total_redundant": total_red,
        "redundant_pct": round(100 * total_red / total_in, 1) if total_in else 0.0,
        "compaction_saved": saved,
        "top_sessions": top,
    }


def detect_redundancy(summary: Dict[str, Any],
                      pct_threshold: float = PCT_THRESHOLD,
                      min_input: int = MIN_INPUT) -> List[Dict[str, Any]]:
    """Signale (REPORT ONLY) les sessions dont le re-envoi de prefixe depasse le seuil.
    Ne propose aucune action : c'est le S16 qui, plus tard, cachera/cloturera."""
    flags: List[Dict[str, Any]] = []
    for s in summary["sessions"]:
        if s.get("measured"):
            continue                       # compactee : on juge sur la mesure reelle, pas le proxy
        if s["in"] < min_input:
            continue
        pct = s["redundant_prefix"] / s["in"] if s["in"] else 0.0
        if pct >= pct_threshold:
            flags.append({
                "session_id": s["session_id"],
                "n_turns": len(s["inputs"]),
                "input": s["in"],
                "redundant": s["redundant_prefix"],
                "pct": round(100 * pct, 1),
            })
    return sorted(flags, key=lambda f: f["redundant"], reverse=True)


def format_report(summary: Dict[str, Any],
                  pct_threshold: float = PCT_THRESHOLD,
                  min_input: int = MIN_INPUT) -> str:
    d = usage_digest(summary)
    flags = detect_redundancy(summary, pct_threshold, min_input)
    tot = d["totals"]
    L = ["Usage: (S15 - mesure, lecture seule)"]
    L.append("-" * 64)
    for (mid, cs), b in sorted(d["by_basis"].items(), key=lambda kv: -kv[1]["in"]):
        L.append(f"  {str(mid):26} [{cs}]  tours={b['turns']:4}  in={b['in']:8}  out={b['out']:8}")
    L.append("-" * 64)
    L.append(f"  CUMUL  tours={tot['turns']}  in={tot['in']}  out={tot['out']}  total={tot['total']}")
    L.append(f"  Re-envoi de prefixe (proxy, sessions PRE-compaction) : {d['total_redundant']} tokens "
             f"= {d['redundant_pct']}% de l'entree")
    saved = d.get("compaction_saved", 0)
    full_eq = tot["in"] + saved
    pct = round(100 * saved / full_eq, 1) if full_eq else 0.0
    L.append(f"  Economie compaction (MESUREE, cloture C3) : {saved} tokens d'entree epargnes "
             f"= {pct}% de ce qui aurait ete envoye")
    L.append("-" * 64)
    compacted = [s for s in summary["sessions"] if s.get("measured") and s["saved"] > 0]
    if compacted:
        L.append("Sessions compactees (economie MESUREE, cloture C3) :")
        for s in sorted(compacted, key=lambda x: -x["saved"]):
            full = s["in"] + s["saved"]
            pct = round(100 * s["saved"] / full, 1) if full else 0.0
            L.append(f"  session {str(s['session_id'])[:8]}  tours={len(s['inputs']):4}  "
                     f"envoye={s['in']:7}  epargne={s['saved']:7} ({pct}% de son entree)")
        L.append("-" * 64)
    if flags:
        L.append(f"Sessions signalees (proxy, LEGACY non compactees ; re-envoi >= {int(pct_threshold*100)}%, in >= {min_input}) :")
        for f in flags:
            L.append(f"  session {str(f['session_id'])[:8]}  tours={f['n_turns']:4}  "
                     f"in={f['input']:8}  re-envoi={f['redundant']:8} ({f['pct']}%)")
    else:
        L.append("Aucune session legacy au-dessus du seuil.")
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser(description="economy S15 : mesure d'usage (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--pct", type=float, default=PCT_THRESHOLD, help="seuil de re-envoi (0-1)")
    p.add_argument("--min-input", type=int, default=MIN_INPUT, dest="min_input")
    args = p.parse_args()
    summary = summarize(read_events(args.journal))
    print(format_report(summary, args.pct, args.min_input))


if __name__ == "__main__":
    main()
