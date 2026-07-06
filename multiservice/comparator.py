"""Comparateur LLM local pour la curation : juge des paires de faits candidats, propose des
consolidations (garder un canonique EXISTANT, clore les variantes) ou confirme des contradictions.

Constitution : LLM **local** uniquement ; il PROPOSE (`pending_human`), n'ecrit rien en memoire ;
il JUGE des faits existants et CHOISIT parmi eux (il n'autorise aucun texte) ; chaque verdict cite
ses preuves ; JSON illisible -> `uncertain` (revue humaine, jamais de proposition a l'aveugle).
PUR vis-a-vis d'un backend injecte : l'appel Ollama est isole dans le backend.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .curator import CLOSURE_SESSION

_RELATIONS = ("equivalent", "different", "contradictory")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = (
    "Tu compares DEUX faits d'un journal de memoire. Reponds STRICTEMENT en JSON sur une ligne, "
    "sans prose autour : {\"relation\": \"equivalent|different|contradictory\", "
    "\"keep\": \"a|b\", \"rationale\": \"...\"}. "
    "equivalent = ils disent la MEME chose (reformulation). different = faits distincts. "
    "contradictory = ils s'opposent. Pour equivalent, 'keep' = le fait le plus complet (a ou b). "
    "Tu ne crees aucun texte : tu choisis parmi a et b."
)


@dataclass
class Verdict:
    relation: str            # equivalent | different | contradictory | uncertain
    keep: Optional[str]      # "a" | "b" | None (pertinent seulement si equivalent)
    rationale: str


def _build_messages(a_text: str, b_text: str, kind: str) -> List[Dict[str, str]]:
    user = (f"Type: {kind}\nFait a: {a_text}\nFait b: {b_text}\nTa reponse JSON:")
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def _parse(text: str) -> Optional[dict]:
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def judge_pair(backend, a_text: str, b_text: str, kind: str) -> Verdict:
    """Verdict LLM sur une paire (`backend.chat(messages) -> Completion`). Robuste : toute
    erreur / JSON illisible / relation inconnue -> `uncertain` (jamais de proposition a l'aveugle)."""
    try:
        c = backend.chat(_build_messages(a_text, b_text, kind))
        d = _parse(getattr(c, "text", "") or "")
    except Exception:
        return Verdict("uncertain", None, "backend error")
    if not d or d.get("relation") not in _RELATIONS:
        return Verdict("uncertain", None, "verdict illisible")
    rel = d["relation"]
    keep = d.get("keep") if rel == "equivalent" else None
    if keep not in ("a", "b"):
        keep = None
    return Verdict(rel, keep, str(d.get("rationale", ""))[:300])


def _older(events: List[dict]) -> dict:
    return min(events, key=lambda e: e.get("valid_from") or "")


def _consolidation(keep: dict, close: dict, kind: str, model: str, rationale: str) -> dict:
    kid, cid = keep["id"], close["id"]
    cmd = (f'memlog-http "Consolidation approuvee (LLM {model}) : reformulations equivalentes, '
           f'garder {kid}, clore {cid}" --kind correction --session {CLOSURE_SESSION} --closes {cid}')
    reject = ('memlog-http "Consolidation REJETEE (faits a garder distincts)" '
              f"--kind note --session curation-reviews --rejects {cid}")
    return {"action": "consolidate", "keep_id": kid, "close_ids": [cid], "kind": kind,
            "rationale": rationale, "evidence": {"keep": keep, "close": close, "judge_model": model},
            "status": "pending_human", "command": cmd, "command_reject": reject}


def _ids(evs: List[dict]) -> List[str]:
    return [e.get("id") for e in evs]


def review_candidates(report: Dict[str, Any], backend, model: Optional[str] = None) -> Dict[str, Any]:
    """Passe les quasi-doublons + contradictions du rapport deterministe au juge LLM.
    Retourne {consolidations, contradictions, dismissed, uncertain, model}. Ne mute RIEN."""
    model = model or getattr(backend, "model_id", "?")
    consolidations: List[dict] = []
    contradictions: List[dict] = []
    dismissed: List[dict] = []
    uncertain: List[dict] = []

    def handle(evs, default_kind, origin):
        a, b = evs
        v = judge_pair(backend, a.get("text", ""), b.get("text", ""), default_kind)
        if v.relation == "equivalent":
            keep = a if v.keep == "a" else (b if v.keep == "b" else _older(evs))
            close = b if keep is a else a
            consolidations.append(_consolidation(keep, close, default_kind, model, v.rationale))
        elif v.relation == "contradictory":
            contradictions.append({"event_ids": _ids(evs), "origin": origin,
                                   "rationale": v.rationale, "events": evs})
        elif v.relation == "different":
            dismissed.append({"event_ids": _ids(evs), "origin": origin, "rationale": v.rationale})
        else:
            uncertain.append({"event_ids": _ids(evs), "origin": origin, "rationale": v.rationale})

    for pair in report.get("near_duplicates", []):
        evs = pair.get("events", [])
        if len(evs) == 2:
            handle(evs, pair.get("type") or evs[0].get("type") or "note", "near")

    for pair in report.get("contradiction_candidates", []):
        evs = pair.get("events", [])
        if len(evs) == 2:
            handle(evs, evs[0].get("type") or "decision", "contradiction")

    return {"consolidations": consolidations, "contradictions": contradictions,
            "dismissed": dismissed, "uncertain": uncertain, "model": model}


def needs_attention(result: Dict[str, Any]) -> bool:
    """Action / revue disponible = au moins une consolidation ou une contradiction confirmee."""
    return bool(result.get("consolidations") or result.get("contradictions"))


def format_llm_review_markdown(result: Dict[str, Any]) -> str:
    """Rend la revue LLM : consolidations (commande prete a coller), contradictions confirmees
    (l'humain resout), ecartes + incertains (transparence, pas de drop silencieux). PUR."""
    cons = result.get("consolidations", [])
    contra = result.get("contradictions", [])
    dis = result.get("dismissed", [])
    unc = result.get("uncertain", [])
    L = [f"# Revue LLM de curation (modele {result.get('model', '?')})", ""]
    if needs_attention(result):
        L.append(f"**{len(cons)} consolidation(s)** proposee(s), "
                 f"**{len(contra)} contradiction(s)** confirmee(s).")
    else:
        L.append("Rien a proposer (aucune consolidation ni contradiction confirmee).")

    if cons:
        L += ["", "## Consolidations (coller pour approuver, C1)"]
        for c in cons:
            L.append(f"- garder `{c['keep_id'][:8]}`, clore `{c['close_ids'][0][:8]}` "
                     f"- {c['rationale'][:80]}")
            L += ["  ```", f"  {c['command']}", "  ```"]
    if contra:
        L += ["", "## Contradictions confirmees (a resoudre par l'humain)"]
        for x in contra:
            ids = ", ".join((i or "")[:8] for i in x.get("event_ids", []))
            L.append(f"- [{ids}] {x.get('rationale', '')[:90]}")
    if dis:
        L += ["", f"## Ecartes ({len(dis)} faux positifs - transparence)"]
        for x in dis:
            ids = ", ".join((i or "")[:8] for i in x.get("event_ids", []))
            L.append(f"- [{ids}] {x.get('rationale', '')[:80]}")
    if unc:
        L += ["", f"## Incertains ({len(unc)} - revue humaine)"]
        for x in unc:
            ids = ", ".join((i or "")[:8] for i in x.get("event_ids", []))
            L.append(f"- [{ids}] {x.get('rationale', '')[:80]}")
    return "\n".join(L) + "\n"
