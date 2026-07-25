"""V1 — RAPPEL PROACTIF : la memoire s'impose au bon moment (acte III, 25/07/2026).

Le constat qui a ouvert l'acte : le piege « builder n'est pas redeployer » etait dans la memoire
UNE HEURE avant que l'erreur soit commise. Il n'a arrete personne. La memoire avait la reponse et
est restee muette, parce qu'elle attend qu'on l'interroge.

Ici, l'inverse : etant donne une commande sur le point d'etre lancee, quels pieges connus mordent ?
Branche a un hook d'agent, cela transforme la memoire de BIBLIOTHEQUE en GARDE-FOU.

Trois regles, dans cet ordre :
  1. **Il avertit, il ne bloque pas.** La memoire observe, elle ne juge ni n'agit (C1).
  2. **Silencieux quand rien ne mord.** Un garde-fou qui crie tout le temps n'est plus lu.
  3. **Rapide.** Il s'intercale avant une action : on ne charge que les pieges, jamais le journal
     entier — ils sont rares par nature, c'est ce qui fait leur valeur.

PUR (le matching) ; I/O au bord (`main`, pour le hook).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from . import memory
from .events import AetherEvent, EventType

# Mots trop frequents pour discriminer : les laisser declencherait sur tout.
_VIDES = {
    "le", "la", "les", "un", "une", "des", "de", "du", "dans", "pas", "ne", "et", "ou", "a", "au",
    "aux", "en", "sur", "pour", "par", "que", "qui", "est", "sont", "ce", "cette", "il", "elle",
    "on", "se", "sa", "son", "ses", "avec", "sans", "plus", "moins", "tout", "tous", "toute",
    "the", "and", "for", "with", "not", "you", "your", "this", "that", "from", "sudo", "echo",
}
_MIN_MOT = 3                    # en-deca, un mot ne discrimine rien (-t, -f, cd, ls...)
_MIN_COMMUNS = 1                # nb de mots significatifs partages pour declencher


def _mots(texte: str) -> set:
    """Mots significatifs d'un texte, normalises. PUR."""
    bruts = re.findall(r"[a-z0-9_.-]+", (texte or "").lower())
    return {m.strip("-._") for m in bruts
            if len(m.strip("-._")) >= _MIN_MOT and m.strip("-._") not in _VIDES}


def pieges_pour_commande(events: List[AetherEvent], commande: str,
                         source_prefix: Optional[str] = None,
                         k: int = 3) -> List[Dict[str, Any]]:
    """Pieges qui mordent sur cette commande, du plus pertinent au moins. PUR, LECTURE SEULE.

    Le matching est LEXICAL et volontairement simple : il doit etre instantane et explicable.
    Un rappel qu'on ne comprend pas est un rappel qu'on ignore."""
    mots_cmd = _mots(commande)
    if not mots_cmd:
        return []
    hits = []
    for e in events:
        if e.type != EventType.PITFALL:
            continue                                  # une decision n'est pas un garde-fou
        if not memory.project_matches(e.data, e.source, source_prefix):
            continue
        texte = memory._text(e)
        communs = mots_cmd & _mots(texte)
        if len(communs) < _MIN_COMMUNS:
            continue
        hits.append({"id": e.id, "text": texte, "score": len(communs),
                     "declencheurs": sorted(communs),
                     "command": (e.data or {}).get("command")})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:k]


def format_avertissement(hits: List[Dict[str, Any]], largeur: int = 300) -> str:
    """Message court et actionnable. Vide si rien ne mord (pas de bruit). PUR."""
    if not hits:
        return ""
    # Sortie console en ASCII PUR (regle du projet) : un tiret cadratin sort en mojibake sous
    # PowerShell, et un avertissement illisible n'avertit personne.
    lignes = ["", "PIEGE DEJA RENCONTRE - la memoire vous arrete une seconde :"]
    for h in hits:
        txt = h["text"].strip()
        if len(txt) > largeur:
            txt = txt[:largeur].rstrip() + "..."
        lignes.append("  - " + txt)
        if h.get("command"):
            lignes.append("    -> " + str(h["command"])[:160])
    lignes.append("")
    return "\n".join(lignes)


def main() -> int:
    """Point d'entree HOOK : lit le contexte de l'agent sur stdin (JSON), avertit sur stdout.

    Ne bloque JAMAIS (code retour 0 quoi qu'il arrive) : un garde-fou defaillant ne doit pas
    empecher de travailler. Silencieux si rien ne mord."""
    import json
    import sys
    from . import config
    from .journal import read_events
    try:
        brut = sys.stdin.read()
        ctx = json.loads(brut) if brut.strip() else {}
    except Exception:
        return 0
    entree = ctx.get("tool_input") or {}
    commande = entree.get("command") or entree.get("file_path") or ""
    if not commande:
        return 0
    try:
        # On ne charge QUE les pieges : rares par nature, donc instantane.
        from . import projection
        try:
            proj = projection.for_journal(config.JOURNAL_PATH, config.PROJECTION_PATH)
            evs = proj.events_by_types(["pitfall"])
        except Exception:
            evs = [e for e in read_events(config.JOURNAL_PATH) if e.type == EventType.PITFALL]
        msg = format_avertissement(pieges_pour_commande(evs, commande))
        if msg:
            print(msg)
    except Exception:
        return 0                                      # jamais bloquant
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
