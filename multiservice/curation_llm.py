"""Revue LLM de curation (CLI, LECTURE SEULE).

Lit le journal synchronise, calcule le rapport de curation DETERMINISTE (`curator`), puis passe
les quasi-doublons / contradictions au **comparateur LLM local** (`comparator`) pour dé-bruiter et
proposer des consolidations. Ecrit `logs/curation/curation-llm-YYYYMMDD.md`. **N'ECRIT RIEN en
memoire** : propositions `pending_human` (les commandes `--closes` sont dans le rapport).

CLI : `python -m multiservice.curation_llm [--journal ...] [--out ...]`.
Modele = choix utilisateur (`config.OLLAMA_MODEL`), jamais fige ; temperature 0 (reproductible).
Backend injectable (tests).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from . import comparator, config, curator
from .journal import read_events

_DEF_OUT = str(Path(__file__).resolve().parent.parent / "logs" / "curation")


def _default_backend():
    from .backends import OllamaBackend
    return OllamaBackend(model=config.OLLAMA_MODEL, host=config.OLLAMA_HOST,
                         timeout=config.OLLAMA_TIMEOUT, options={"temperature": 0})


# --- jugement BORNE (25/07/2026) : une tache planifiee doit toujours ABOUTIR -----------------
#
# Constat : le jugement a tourne plus de 40 min sans rien produire, puis a ete interrompu —
# sortie vide, aucun rapport. Le defaut n'est pas la lenteur, c'est le TOUT OU RIEN : on juge les
# 46 candidats puis on ecrit a la fin. Interrompu a 95 %, il ne reste rien, et une tache
# hebdomadaire qui n'aboutit jamais echoue en silence chaque semaine.
#
# Remede, meme principe que le depot d'etat : borner le lot, ecrire a chaque passage, et retenir
# ce qui a deja ete juge pour que la file se vide au lieu de tourner en rond.

MAX_PAIRES_DEFAUT = 10
_JUGES_FICHIER = "paires-jugees.json"


def empreinte_paire(paire: dict) -> str:
    """Identite d'une paire, INDEPENDANTE de l'ordre : (a,b) et (b,a) sont la meme paire —
    sinon on la rejuge indefiniment. PUR."""
    ids = sorted(str(e.get("id", "")) for e in (paire.get("events") or []))
    return "|".join(ids)


def deja_juges(dossier) -> set:
    """Empreintes deja jugees. Ne LEVE jamais : un depot absent ou illisible ne doit pas
    empecher de juger."""
    import json
    from pathlib import Path as _P
    try:
        return set(json.loads((_P(dossier) / _JUGES_FICHIER).read_text(encoding="utf-8")))
    except Exception:
        return set()


def deposer_juges(dossier, empreintes) -> None:
    """Memorise les paires jugees (ecriture atomique)."""
    import json
    from pathlib import Path as _P
    d = _P(dossier)
    d.mkdir(parents=True, exist_ok=True)
    cible = d / _JUGES_FICHIER
    tmp = cible.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted(empreintes)), encoding="utf-8")
    tmp.replace(cible)


def selectionner(report: dict, deja: set, max_paires: int = MAX_PAIRES_DEFAUT) -> dict:
    """Rapport restreint a une TRANCHE de candidats non encore juges. PUR.
    Les `counts` restent le total REEL : une tranche traitee ne doit pas faire croire que la
    file est vide."""
    restant_total = 0
    tranche = dict(report)
    budget = max(0, max_paires)
    for cle in ("near_duplicates", "contradiction_candidates"):
        candidats = [p for p in (report.get(cle) or []) if empreinte_paire(p) not in deja]
        restant_total += len(candidats)
        pris = candidats[:budget]
        budget -= len(pris)
        tranche[cle] = pris
    tranche["counts"] = dict(report.get("counts") or {})
    tranche["restant"] = restant_total - sum(len(tranche.get(c) or [])
                                             for c in ("near_duplicates",
                                                       "contradiction_candidates"))
    return tranche


def marquer_traitees(dossier, tranche: dict) -> set:
    """Ajoute les paires de la tranche aux deja-jugees. Retourne les empreintes ajoutees."""
    ajoutees = {empreinte_paire(p)
                for cle in ("near_duplicates", "contradiction_candidates")
                for p in (tranche.get(cle) or [])}
    deposer_juges(dossier, deja_juges(dossier) | ajoutees)
    return ajoutees


def run(journal_path: str, out_dir: str, backend=None,
        now: Optional[datetime] = None,
        max_paires: int = MAX_PAIRES_DEFAUT) -> Tuple[str, bool, dict]:
    """Genere la revue LLM datee. Retourne (chemin, needs_attention, result).
    LECTURE SEULE sur la memoire (aucun append). Backend injecte pour les tests.
    Juge au plus `max_paires` candidats non encore vus : la tache ABOUTIT toujours."""
    now = now or datetime.now(timezone.utc)
    backend = backend or _default_backend()
    report = curator.curation_report(read_events(journal_path), now=now)
    tranche = selectionner(report, deja_juges(out_dir), max_paires)
    result = comparator.review_candidates(tranche, backend)
    result["restant"] = tranche.get("restant", 0)
    marquer_traitees(out_dir, tranche)
    md = comparator.format_llm_review_markdown(result)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curation-llm-{now.strftime('%Y%m%d')}.md"
    path.write_text(md, encoding="utf-8")
    return str(path), comparator.needs_attention(result), result


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Revue LLM locale de curation (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--out", default=_DEF_OUT)
    p.add_argument("--max-paires", dest="max_paires", type=int, default=MAX_PAIRES_DEFAUT,
                   help="candidats juges par passage (la tache doit ABOUTIR)")
    a = p.parse_args()
    path, needs, r = run(a.journal, a.out, max_paires=a.max_paires)
    tag = "ACTION" if needs else "ok"                    # sortie ASCII (regle console)
    print(f"[{tag}] revue LLM -> {path} | consolidations={len(r['consolidations'])} "
          f"contradictions={len(r['contradictions'])} ecartes={len(r['dismissed'])} "
          f"incertains={len(r['uncertain'])} restant={r.get('restant', 0)} "
          f"(modele {r['model']})")


if __name__ == "__main__":
    main()
