"""Rapport de curation PLANIFIE (lecture seule).

Lit le journal (local synchronise, tenu frais par la tache MSIA_sync_merge), calcule le
rapport de curation et l'ecrit en markdown date. **N'ECRIT RIEN en memoire** : la curation
OBSERVE et PROPOSE (les clotures pretes sont dans le rapport, coller = approuver, C1) ;
l'humain tranche. Silencieux quand rien n'est actionnable (anti-bruit).

CLI : `python -m multiservice.curation_report [--journal ...] [--out ...]`.
Concu pour une tache planifiee (MSIA_curation_report, quotidienne).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from . import config, curator
from .journal import read_events

# Racine repo (multiservice/..) -> logs/curation par defaut.
_DEF_OUT = str(Path(__file__).resolve().parent.parent / "logs" / "curation")


def run(journal_path: str, out_dir: str,
        now: Optional[datetime] = None) -> Tuple[str, bool, dict]:
    """Genere le rapport markdown date. Retourne (chemin, needs_attention, counts).
    LECTURE SEULE : ne touche jamais le journal (aucun append). IO au bord (ecrit le .md)."""
    now = now or datetime.now(timezone.utc)
    report = curator.curation_report(read_events(journal_path), now=now)
    md = curator.format_report_markdown(report)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curation-{now.strftime('%Y%m%d')}.md"
    path.write_text(md, encoding="utf-8")
    # Depose l'etat pour relecture INSTANTANEE par `resume` : le calcul coute 84 s, une reprise
    # ne peut pas le refaire. La tache calcule lentement une fois par jour, la reprise lit.
    # Emplacement CANONIQUE (`config.CURATION_DIR`), pas le dossier des rapports : sinon la tache
    # depose dans une boite aux lettres et la reprise en ouvre une autre (bug du 25/07).
    deposer_etat(config.CURATION_DIR, {"as_of": now.isoformat(), "counts": report["counts"],
                                       "proposals": report.get("proposals", [])})
    return str(path), curator.report_needs_attention(report), report["counts"]


# --- depot / relecture de l'etat de curation (fermeture de la boucle, 25/07/2026) ---
#
# Pourquoi un depot : `curation_report` coute 84 s sur le corpus reel (comparaison de paires) et
# le jugement LLM plus de 10 min. Impossible a recalculer dans une reprise. La tache calcule
# LENTEMENT une fois par jour et depose ; `resume` LIT (cout nul) et met sous les yeux.

ETAT_FICHIER = "etat-curation.json"


def deposer_etat(dossier, etat: dict):
    """Depose l'etat de curation pour relecture instantanee. Ecriture ATOMIQUE : une reprise ne
    doit jamais lire un etat a moitie ecrit."""
    import json
    d = Path(dossier)
    d.mkdir(parents=True, exist_ok=True)
    cible = d / ETAT_FICHIER
    tmp = cible.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(cible)
    return cible


def dernier_etat(dossier):
    """Dernier etat depose, ou None. Ne LEVE JAMAIS : une curation absente ou illisible ne doit
    pas empecher de reprendre le travail."""
    import json
    p = Path(dossier) / ETAT_FICHIER
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Rapport de curation planifie (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--out", default=_DEF_OUT)
    a = p.parse_args()
    path, needs, c = run(a.journal, a.out)
    tag = "ACTION" if needs else "ok"                    # sortie ASCII (regle console)
    print(f"[{tag}] curation -> {path} | exact_dup={c['exact_duplicates']} "
          f"gabarits={c['placeholder_facts']} near={c['near_duplicates']} "
          f"contra={c['contradiction_candidates']} stale={c['stale_candidates']}")


if __name__ == "__main__":
    main()

