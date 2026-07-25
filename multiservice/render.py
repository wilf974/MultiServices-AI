"""Documents comme PROJECTIONS de la memoire — une seule ecriture, plusieurs vues.

Constat du 24-25/07/2026 : pour chaque chantier, la meme information etait ecrite TROIS fois —
`memlog-http` (le fait), `docs/DECISIONS.md` (la version longue), le coffre Obsidian (la note).
Trois formats, trois risques de divergence, trois fois le travail. Et ils divergent deja.

C'est la doctrine journal/projection appliquee a la documentation : la memoire est la SOURCE, le
markdown une VUE derivee et regenerable.

NUANCE DECISIVE : un document contient aussi de la prose que le journal n'a pas (doctrine,
design, arbitrages longs). On ne regenere donc JAMAIS un fichier entier — on regenere une SECTION
delimitee, comme le fait deja le bloc `OBSIDIAN+MCP-OBLIGATOIRE` de CLAUDE.md.
**Les faits sont generes, les essais restent ecrits.**

PUR (le rendu) ; I/O au bord (`ecrire_section`). LECTURE SEULE cote memoire : ne touche jamais
le journal.

    python -m multiservice.render --projet project:multiservice --vers docs/JOURNAL.md
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, memory
from .events import AetherEvent, EventType

DEBUT = "<!-- MEMOIRE:DEBUT (genere depuis le journal — ne pas editer a la main) -->"
FIN = "<!-- MEMOIRE:FIN -->"

_TYPES_RENDUS = (EventType.DECISION, EventType.CORRECTION, EventType.PITFALL,
                 EventType.VALIDATION, EventType.HYPOTHESIS, EventType.OBSERVATION)
_ETIQUETTE = {"decision": "Décision", "correction": "Correction", "pitfall": "⚠ Piège",
              "validation": "Validation", "hypothesis": "Hypothèse", "observation": "Observation"}


def render_markdown(events: List[AetherEvent], project: str,
                    days: Optional[int] = None, now: Optional[datetime] = None,
                    k: Optional[int] = None) -> str:
    """Vue markdown des faits d'un projet, du plus RECENT au plus ancien. PUR.

    Rend les champs structures (`rationale` / `pitfall` / `command` / `refs`) en markdown lisible :
    c'est tout l'interet d'avoir cesse d'encoder la structure en prose. Une decision revisee est
    SIGNALEE, jamais tue — un document qui tait ses revisions ment par omission (C3)."""
    asof = memory._aware(now) or datetime.now(timezone.utc)
    closes_idx = memory._closes_index(events, as_of=asof)
    floor = datetime.min.replace(tzinfo=timezone.utc)

    retenus = []
    for e in events:
        if e.type not in _TYPES_RENDUS:
            continue
        if not memory.project_matches(e.data, e.source, project):
            continue
        vf = memory._aware(e.valid_from)
        if vf and vf > asof:
            continue
        if days is not None and vf and (asof - vf).days > days:
            continue
        retenus.append(e)
    retenus.sort(key=lambda e: (memory._aware(e.valid_from) or floor), reverse=True)
    if k:
        retenus = retenus[:k]

    lignes = [DEBUT, "",
              "> Section **générée** depuis la mémoire (`python -m multiservice.render`).",
              f"> Projet `{project}` · {len(retenus)} fait(s) · au {asof.strftime('%d/%m/%Y %H:%M')} UTC.",
              "> Toute modification manuelle ici sera écrasée : le fait vit dans le journal.", ""]
    if not retenus:
        lignes += ["*Aucun fait journalisé pour ce projet.*", "", FIN]
        return "\n".join(lignes)

    for e in retenus:
        vf = memory._aware(e.valid_from)
        date = vf.strftime("%d/%m/%Y") if vf else "?"
        corrected = memory._closed_by(closes_idx, e.id)
        etiq = _ETIQUETTE.get(e.type.value, e.type.value)
        titre = f"### {date} — {etiq}"
        if corrected:
            titre += "  *(révisé depuis)*"
        lignes += [titre, "", memory._text(e).strip(), ""]
        st = memory._structure(e)
        if st.get("rationale"):
            lignes += [f"**Pourquoi.** {st['rationale']}", ""]
        if st.get("pitfall"):
            lignes += [f"**⚠ Piège.** {st['pitfall']}", ""]
        if st.get("command"):
            lignes += ["```", st["command"], "```", ""]
        if st.get("refs"):
            lignes += ["*Réf. : " + " · ".join(f"`{r}`" for r in st["refs"]) + "*", ""]
        lignes += [f"<sub>`{e.id}` · source `{e.source}` · session `{e.data.get('session_id')}`</sub>",
                   ""]
    lignes.append(FIN)
    return "\n".join(lignes)


def ecrire_section(chemin, events: List[AetherEvent], project: str, **kw) -> Path:
    """Remplace la SECTION generee du fichier (entre marqueurs), sans toucher au reste.

    Fichier sans marqueurs -> la section est ajoutee a la fin (on n'ecrase jamais de la prose).
    Fichier absent -> cree. Idempotent : regenerer deux fois donne le meme fichier, sinon chaque
    generation pollue le diff git et on cesse de s'en servir."""
    p = Path(chemin)
    section = render_markdown(events, project, **kw)
    if p.exists():
        contenu = p.read_text(encoding="utf-8")
        if DEBUT in contenu and FIN in contenu:
            avant = contenu[:contenu.index(DEBUT)]
            apres = contenu[contenu.index(FIN) + len(FIN):]
            neuf = avant + section + apres
        else:
            neuf = contenu.rstrip("\n") + "\n\n" + section + "\n"
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        neuf = section + "\n"
    p.write_text(neuf, encoding="utf-8")
    return p


def main() -> int:
    import argparse
    from .journal import read_events
    p = argparse.ArgumentParser(description="Rend les faits d'un projet en markdown (lecture seule).")
    p.add_argument("--projet", required=True)
    p.add_argument("--vers", default=None, help="fichier a mettre a jour (sinon : sortie standard)")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--jours", type=int, default=None)
    p.add_argument("--k", type=int, default=None)
    a = p.parse_args()
    evs = read_events(a.journal)
    if a.vers:
        cible = ecrire_section(a.vers, evs, a.projet, days=a.jours, k=a.k)
        print("[render] section mise a jour -> %s" % cible)
    else:
        print(render_markdown(evs, a.projet, days=a.jours, k=a.k))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
