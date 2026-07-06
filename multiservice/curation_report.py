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
    return str(path), curator.report_needs_attention(report), report["counts"]


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
