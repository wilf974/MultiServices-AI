"""Sprint 17 - Skills emergentes (DETECTION, lecture seule).

On cristallise des candidates de skill a partir des patterns REELS d'usage. v1 (D10) :
  - OBSERVE SEUL : on ne regarde que les prompts source=user (jamais une candidate
    proposee par le LLM - separation par source, anti-empoisonnement) ;
  - seuil de recurrence >= 3 (BITS : ne jamais cristalliser sur du bruit) ;
  - confiance = 1 - 0.5^n (meme courbe que experience.py / l'Experience Engine) ;
  - SUGGESTION seule : type=suggestion. La promotion en skill est HUMAINE (hors de ce
    module). Ce module n'ecrit rien, ne mute rien (test structurel).

Regroupement deterministe par signature de tokens (>= 2 tokens significatifs partages),
transpose de experience.build_patterns.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Set, Tuple

from .events import AetherEvent, EventType

# mots vides FR courants (repris/etendus depuis experience.py)
_STOP = frozenset(
    "le la les un une des de du d l au aux et ou est sont a as ai aie avez avons ont "
    "sur dans pour par avec sans plus tres moins peux peut peuvent tu je il elle on nous vous "
    "ce cet cette ces mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs "
    "que qui quoi quel quelle quels quelles comment pourquoi quand dont ou "
    "fait faire fais font me te se y en "
    "pas via moi toi lui eux ni si car donc mais or comme tout tous toute toutes "
    "bien faut veux veut veulent dois doit etre avoir cela ceci ca autre autres "
    "meme memes aussi alors ici oui non merci stp svp "
    "the to of and is are can you your this that with for from".split()
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> Set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9_.-]+", _norm(text))
            if len(t) >= 3 and t not in _STOP}


def _user_prompts(events: List[AetherEvent]) -> List[Tuple[str, str]]:
    """(id, texte) des prompts OBSERVES (source user). Jamais de contenu propose-LLM."""
    out = []
    for e in events:
        if e.type == EventType.PROMPT and (e.source or "").startswith("user"):
            out.append((e.id, e.data.get("text", "")))
    return out


def _confidence(n: int) -> float:
    return round(min(0.95, 1.0 - 0.5 ** max(n, 1)), 2)


def _cluster(prompts: List[Tuple[str, str]], min_overlap: int = 2) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for pid, text in prompts:
        toks = _tokens(text)
        if len(toks) < min_overlap:
            continue                       # trop court pour signer un pattern
        best, best_ov = None, 0
        for c in clusters:
            ov = len(toks & c["signature"])
            if ov >= min_overlap and ov > best_ov:
                best, best_ov = c, ov
        if best is None:
            clusters.append({"signature": set(toks), "ids": [pid], "samples": [text]})
        else:
            inter = best["signature"] & toks
            best["signature"] = inter or best["signature"]   # converge, jamais vide
            best["ids"].append(pid)
            best["samples"].append(text)
    return clusters


def skill_candidates(events: List[AetherEvent], min_occurrences: int = 3,
                     min_overlap: int = 2) -> List[Dict[str, Any]]:
    """Patterns de prompts recurrents -> candidates (type=suggestion). PUR, lecture seule."""
    cands = []
    for c in _cluster(_user_prompts(events), min_overlap=min_overlap):
        n = len(c["ids"])
        if n >= min_occurrences:
            cands.append({
                "type": "suggestion",
                "signature": "+".join(sorted(c["signature"])),
                "count": n,
                "confidence": _confidence(n),
                "evidence": c["ids"][:8],
                "samples": c["samples"][:3],
            })
    return sorted(cands, key=lambda x: (-x["count"], x["signature"]))


def format_candidates(cands: List[Dict[str, Any]]) -> str:
    if not cands:
        return "Aucune skill candidate (aucun pattern de prompt vu >= 3 fois)."
    L = ["Skills candidates (SUGGESTION seule - promotion humaine requise) :", "-" * 64]
    for c in cands:
        L.append(f"  [{c['signature']}]  vu {c['count']}x  confiance={c['confidence']}")
        L.append(f"      ex: {c['samples'][0][:70]}")
    L.append("-" * 64)
    L.append("Pour promouvoir : c'est TOI qui decides (ecrire un SKILL.md). v1 = observe seul.")
    return "\n".join(L)


def main() -> None:
    import argparse
    from . import config
    from .journal import read_events
    p = argparse.ArgumentParser(description="Skills emergentes S17 (detection, lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--min", type=int, default=3, dest="min_occurrences",
                   help="recurrence minimale avant de suggerer (defaut 3, BITS)")
    p.add_argument("--min-overlap", type=int, default=2, dest="min_overlap",
                   help="tokens significatifs partages pour regrouper (defaut 2 ; 3 = plus strict)")
    args = p.parse_args()
    print(format_candidates(skill_candidates(read_events(args.journal),
                                             args.min_occurrences, args.min_overlap)))


if __name__ == "__main__":
    main()
