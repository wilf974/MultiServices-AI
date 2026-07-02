"""IA de curation de la memoire — Phase 1 : detecteurs DETERMINISTES, LECTURE SEULE.

Cadrage <user> 02/07/2026 (docs/curation/) ; spec docs/superpowers/specs/
2026-07-02-curation-memoire-design.md. La curation OBSERVE et PROPOSE ; elle n'ecrit
RIEN (les propositions Phase 2 portent status=pending_human, l'humain tranche — C1).
Corriger = clore/superseder, JAMAIS supprimer (C3). Tout est PUR :
List[AetherEvent] -> rapport JSON-serialisable, preuves attachees (ids, dates — C2).

Calibrage : seuils par DEFAUT (near 0.85, contradiction 0.5, stale 30 j) a recalibrer
sur le premier rapport reel (discipline BITS : jamais a l'aveugle).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .events import AetherEvent, EventType
from .hygiene import looks_like_placeholder
from .memory import (_aware, _corrections_index, _source_matches,
                     _superseded_by, _text)
from .skills import _norm, _tokens

# Types « faits rediges » soumis a curation (jamais les tours bruts de chat).
CURATED_TYPES = {EventType.DECISION, EventType.CORRECTION, EventType.NOTE,
                 EventType.OBSERVATION, EventType.VALIDATION, EventType.HYPOTHESIS}


def _valid_at(e: AetherEvent, asof: datetime) -> bool:
    """Filtre bi-temporel C3 : valide a `asof` (pas encore clos)."""
    vf = _aware(e.valid_from)
    if vf and vf > asof:
        return False
    vt = _aware(e.valid_to)
    return not (vt and vt < asof)


def _facts(events: List[AetherEvent], asof: datetime,
           source_prefix: Optional[str]) -> List[AetherEvent]:
    """Les faits rediges VALIDES (types soumis a curation, texte non vide, filtre source)."""
    out = []
    for e in events:
        if e.type not in CURATED_TYPES:
            continue
        if not _source_matches(e.source, source_prefix):
            continue
        if not _valid_at(e, asof):
            continue
        if not _text(e).strip():
            continue
        out.append(e)
    return out


def _brief(e: AetherEvent) -> Dict[str, Any]:
    """Vue courte d'un evenement-preuve (C2 : id + source + date + session)."""
    vf = _aware(e.valid_from)
    return {"id": e.id, "type": e.type.value, "source": e.source,
            "session_id": e.data.get("session_id"),
            "valid_from": vf.isoformat() if vf else None,
            "text": _text(e)[:160]}


def _jaccard(a: str, b: str) -> float:
    """Recouvrement lexical de deux textes (tokens distincts, accent-insensible). PUR."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return round(inter / union, 4) if union else 0.0


def find_exact_duplicates(events: List[AetherEvent], as_of: Optional[datetime] = None,
                          source_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Groupes de faits VALIDES de meme type au texte normalise IDENTIQUE (>= 2).
    Cas reel : la correction 'licence Apache-2.0' journalisee 2 fois. LECTURE SEULE."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    groups: Dict[Tuple[str, str], List[AetherEvent]] = {}
    for e in _facts(events, asof, source_prefix):
        key = (e.type.value, _norm(_text(e)).strip())
        groups.setdefault(key, []).append(e)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    out = []
    for (typ, _), evs in groups.items():
        if len(evs) < 2:
            continue
        evs = sorted(evs, key=lambda e: _aware(e.valid_from) or floor)
        out.append({"type": typ, "count": len(evs),
                    "text": _text(evs[0])[:160],
                    "events": [_brief(e) for e in evs]})
    out.sort(key=lambda g: g["count"], reverse=True)
    return out


def find_near_duplicates(events: List[AetherEvent], threshold: float = 0.85,
                         as_of: Optional[datetime] = None,
                         source_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Paires de faits VALIDES de meme type au recouvrement lexical >= threshold,
    HORS doublons exacts (textes normalises differents). LECTURE SEULE."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    facts = _facts(events, asof, source_prefix)
    out = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a, b = facts[i], facts[j]
            if a.type != b.type:
                continue
            na, nb = _norm(_text(a)).strip(), _norm(_text(b)).strip()
            if na == nb:                          # doublon EXACT : autre section
                continue
            sim = _jaccard(_text(a), _text(b))
            if sim >= threshold:
                out.append({"type": a.type.value, "similarity": sim,
                            "events": [_brief(a), _brief(b)]})
    out.sort(key=lambda p: p["similarity"], reverse=True)
    return out


def find_placeholder_facts(events: List[AetherEvent], as_of: Optional[datetime] = None,
                           source_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Faits VALIDES dont le texte est un gabarit non rempli (pollution observee :
    '<sujet>' encore en still_standing). Candidats naturels a la cloture. LECTURE SEULE."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    return [_brief(e) for e in _facts(events, asof, source_prefix)
            if looks_like_placeholder(_text(e))]


def find_stale_candidates(events: List[AetherEvent], now: Optional[datetime] = None,
                          older_than_days: int = 30,
                          source_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Decisions VALIDES, non corrigees (C3), plus vieilles que `older_than_days` :
    candidates a une revue humaine. Heuristique d'AGE seulement — on ne juge pas le
    contenu (la memoire observe, l'humain tranche). LECTURE SEULE."""
    asof = _aware(now) or datetime.now(timezone.utc)
    cutoff = asof - timedelta(days=older_than_days)
    corr_idx = _corrections_index(events)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    out = []
    for e in _facts(events, asof, source_prefix):
        if e.type != EventType.DECISION:
            continue
        vf = _aware(e.valid_from)
        if vf is None or vf >= cutoff:
            continue
        if _superseded_by(corr_idx, e.data.get("session_id"), vf):
            continue                              # deja revisee : pas un candidat
        d = _brief(e)
        d["age_days"] = int((asof - vf).total_seconds() // 86400)
        out.append(d)
    out.sort(key=lambda d: d.get("age_days", 0), reverse=True)
    return out


def find_contradiction_candidates(events: List[AetherEvent], min_overlap: float = 0.5,
                                  as_of: Optional[datetime] = None,
                                  source_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Paires de DECISIONS VALIDES de la MEME session au recouvrement >= min_overlap :
    redondance OU contradiction — l'humain (ou un LLM local en Phase 2) tranche.
    Textes identiques exclus (section doublons). LECTURE SEULE."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    by_session: Dict[Any, List[AetherEvent]] = {}
    for e in _facts(events, asof, source_prefix):
        if e.type != EventType.DECISION:
            continue
        sid = e.data.get("session_id")
        if sid is None:
            continue
        by_session.setdefault(sid, []).append(e)
    out = []
    for sid, evs in by_session.items():
        evs = sorted(evs, key=lambda e: _aware(e.valid_from) or floor)
        for i in range(len(evs)):
            for j in range(i + 1, len(evs)):
                a, b = evs[i], evs[j]
                if _norm(_text(a)).strip() == _norm(_text(b)).strip():
                    continue
                sim = _jaccard(_text(a), _text(b))
                if sim >= min_overlap:
                    out.append({"session_id": sid, "overlap": sim,
                                "events": [_brief(a), _brief(b)]})
    out.sort(key=lambda p: p["overlap"], reverse=True)
    return out


def make_proposal(action: str, targets: List[str], keep: Optional[str],
                  rationale: str, evidence: Optional[Dict[str, Any]] = None,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Schema d'une PROPOSITION de curation (Phase 2). N'ECRIT RIEN : status
    pending_human, l'humain approuve/rejette (C1). Cloture, jamais suppression (C3)."""
    ts = _aware(now) or datetime.now(timezone.utc)
    return {
        "action": action,                          # close_duplicate | supersede | review
        "targets": list(targets),                  # a clore (valid_to), jamais supprimes
        "keep": keep,                              # le survivant (le plus ancien)
        "rationale": rationale,
        "evidence": evidence or {},
        "status": "pending_human",                 # -> approved | rejected (humain)
        "proposed_at": ts.isoformat(),
    }


def curation_report(events: List[AetherEvent], now: Optional[datetime] = None,
                    source_prefix: Optional[str] = None, k: int = 20,
                    older_than_days: int = 30,
                    near_threshold: float = 0.85) -> Dict[str, Any]:
    """Rapport de curation Phase 1 (LECTURE SEULE, PUR, borne). Sections plafonnees a
    `k`, compteurs COMPLETS, `truncated` signale la coupe (pattern economie de sortie).
    `proposals` : uniquement pour les doublons EXACTS (risque minimal), pending_human."""
    asof = _aware(now) or datetime.now(timezone.utc)
    kk = None if k is None else max(0, k)
    exact = find_exact_duplicates(events, as_of=asof, source_prefix=source_prefix)
    near = find_near_duplicates(events, threshold=near_threshold, as_of=asof,
                                source_prefix=source_prefix)
    placeholders = find_placeholder_facts(events, as_of=asof, source_prefix=source_prefix)
    stale = find_stale_candidates(events, now=asof, older_than_days=older_than_days,
                                  source_prefix=source_prefix)
    contra = find_contradiction_candidates(events, as_of=asof, source_prefix=source_prefix)
    proposals = []
    for g in exact:
        ids = [ev["id"] for ev in g["events"]]
        proposals.append(make_proposal(
            "close_duplicate", targets=ids[1:], keep=ids[0],
            rationale=(f"{g['count']} evenements {g['type']} au texte identique ; "
                       "garder l'original, clore les copies (C3)."),
            evidence={"detector": "exact_duplicates", "score": 1.0,
                      "sessions": sorted({ev["session_id"] for ev in g["events"]
                                          if ev["session_id"]})},
            now=asof))
    counts = {"exact_duplicates": len(exact), "near_duplicates": len(near),
              "placeholder_facts": len(placeholders), "stale_candidates": len(stale),
              "contradiction_candidates": len(contra), "proposals": len(proposals)}
    return {
        "as_of": asof.isoformat(),
        "params": {"source": source_prefix, "k": k, "older_than_days": older_than_days,
                   "near_threshold": near_threshold},
        "counts": counts,
        "truncated": bool(kk is not None and any(v > kk for v in counts.values())),
        "exact_duplicates": exact[:kk],
        "near_duplicates": near[:kk],
        "placeholder_facts": placeholders[:kk],
        "stale_candidates": stale[:kk],
        "contradiction_candidates": contra[:kk],
        "proposals": proposals[:kk],
    }
